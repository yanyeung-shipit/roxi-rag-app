@app.route('/add_topic_pages', methods=['POST'])
def add_topic_pages():
    """Add multiple rheum.reviews topic pages at once. Memory-optimized version with incremental processing."""
    try:
        # Try to get data from JSON or form data
        topics = None
        
        # Check if we have JSON data
        if request.is_json:
            data = request.get_json()
            if data and 'topics' in data:
                topics = data['topics']
        
        # If not JSON, try form data with topic_list
        if topics is None and request.form:
            topic_list = request.form.get('topic_list', '')
            if topic_list:
                # Split by newlines and filter empty lines
                topics = [t.strip() for t in topic_list.split('\n') if t.strip()]
        
        # If still no topics, check direct form data
        if topics is None and request.form and 'topics' in request.form:
            topics_str = request.form.get('topics')
            if topics_str:
                # Try to parse as JSON string
                try:
                    topics = json.loads(topics_str)
                except json.JSONDecodeError:
                    # If not JSON, treat as comma-separated or newline-separated list
                    if ',' in topics_str:
                        topics = [t.strip() for t in topics_str.split(',') if t.strip()]
                    else:
                        topics = [t.strip() for t in topics_str.split('\n') if t.strip()]
        
        # Final validation
        if not topics:
            return jsonify({
                'success': False,
                'message': 'No topics provided. Please include a list of topic names.'
            }), 400
        
        # Ensure topics is a list
        if not isinstance(topics, list):
            topics = [topics]
        if not isinstance(topics, list) or len(topics) == 0:
            return jsonify({
                'success': False,
                'message': 'Topics must be provided as a non-empty list.'
            }), 400
            
        # Check if a collection was specified
        collection_id = request.form.get('collection_id')
        collection = None
        if collection_id and collection_id.strip():
            try:
                # Find the collection
                collection = db.session.get(Collection, int(collection_id))
                if not collection:
                    logger.warning(f"Collection with ID {collection_id} not found")
            except Exception as e:
                logger.error(f"Error finding collection: {e}")
        
        # IMPROVED APPROACH: Process just the first topic in this request with initial batch
        # Additional topics and remaining chunks will be processed in the background
        first_topic = topics[0]
        remaining_topics = topics[1:] if len(topics) > 1 else []
        
        # Set to store successfully created document IDs for background processing
        document_ids_for_background = []
        
        # Clean the topic name for URL
        topic_slug = first_topic.strip().lower().replace(' ', '-')
        if not topic_slug:
            return jsonify({
                'success': False, 
                'message': f'Invalid topic name: "{first_topic}"'
            }), 400
                
        url = f"https://rheum.reviews/topic/{topic_slug}/"
        
        try:
            # Create a new document record in the database
            new_document = Document(
                filename=url,
                title=f"Topic: {first_topic}",  # Will update with proper title after scraping
                file_type="website",
                source_url=url,
                processed=False
            )
            
            db.session.add(new_document)
            db.session.commit()
            logger.info(f"Created document record with ID {new_document.id} for topic {first_topic}")
            
            # Add to collection if specified
            if collection:
                try:
                    collection.documents.append(new_document)
                    db.session.commit()
                    logger.info(f"Added document {new_document.id} to collection {collection_id}")
                except Exception as collection_error:
                    logger.error(f"Error adding document to collection: {collection_error}")
            
            # Get initial content to avoid timeout
            try:
                # Fetch content - optimized for memory
                chunks = create_minimal_content_for_topic(url)
                
                if not chunks or len(chunks) == 0:
                    return jsonify({
                        'success': False,
                        'message': f'Failed to extract content for topic {first_topic}'
                    }), 500
                
                # Update document with title and metadata
                if 'title' in chunks[0]['metadata']:
                    new_document.title = chunks[0]['metadata']['title']
                    db.session.commit()
                
                # Store total available chunks in file_size field (for load_more_content)
                total_chunks = len(chunks)
                new_document.file_size = total_chunks
                db.session.commit()
                
                # IMPROVEMENT 1: Only process a small initial batch (max 30 chunks) for immediate feedback
                # The rest will be processed in the background
                initial_batch_size = min(30, len(chunks))
                initial_chunks = chunks[:initial_batch_size]
                
                # Save the initial batch to database and vector store
                chunk_records = []
                for i, chunk in enumerate(initial_chunks):
                    # Add to vector store
                    vector_store.add_text(chunk['text'], chunk['metadata'])
                    
                    # Create database record
                    chunk_record = DocumentChunk(
                        document_id=new_document.id,
                        chunk_index=i,
                        page_number=chunk['metadata'].get('page_number', 1),
                        text_content=chunk['text']
                    )
                    chunk_records.append(chunk_record)
                
                # Save all records to database
                db.session.add_all(chunk_records)
                db.session.commit()
                
                # Save vector store after initial batch
                vector_store._save()
                
                # Partially mark as processed but queue for background processing
                # Will fully process the remaining chunks in the background
                if len(chunks) > initial_batch_size:
                    # Mark original document for continued background processing
                    new_document.processed = False
                    
                    # Add special processing_state field to track progress
                    new_document.processing_state = json.dumps({
                        "total_chunks": total_chunks,
                        "processed_chunks": initial_batch_size,
                        "status": "processing"
                    })
                    db.session.commit()
                    
                    # Add to background processing queue
                    document_ids_for_background.append(new_document.id)
                else:
                    # Small document, mark as fully processed
                    new_document.processed = True
                    new_document.processing_state = json.dumps({
                        "total_chunks": total_chunks,
                        "processed_chunks": total_chunks,
                        "status": "completed"
                    })
                    db.session.commit()
                
                # Queue any remaining topics for background processing
                remaining_document_ids = []
                for next_topic in remaining_topics:
                    try:
                        # Create document records for remaining topics
                        next_slug = next_topic.strip().lower().replace(' ', '-')
                        if not next_slug:
                            continue
                            
                        next_url = f"https://rheum.reviews/topic/{next_slug}/"
                        
                        # Create a new document record
                        next_document = Document(
                            filename=next_url,
                            title=f"Topic: {next_topic}",
                            file_type="website",
                            source_url=next_url,
                            processed=False,
                            # Mark explicitly for background processing
                            processing_state=json.dumps({
                                "total_chunks": 0,  # Will be determined during processing
                                "processed_chunks": 0,
                                "status": "queued"
                            })
                        )
                        
                        db.session.add(next_document)
                        db.session.commit()
                        
                        # Add to collection if specified
                        if collection:
                            collection.documents.append(next_document)
                            db.session.commit()
                        
                        # Add to background processing queue
                        remaining_document_ids.append(next_document.id)
                    except Exception as next_error:
                        logger.error(f"Error queueing topic {next_topic}: {str(next_error)}")
                
                # All remaining documents will be processed by the background processor
                
                # Get accurate chunk count for the first document
                db.session.refresh(new_document)
                actual_chunk_count = len(new_document.chunks)
                
                # Create response message
                response_data = {
                    'success': True,
                    'document_id': new_document.id, 
                    'topic': first_topic,
                    'url': url,
                    'initial_chunks_processed': actual_chunk_count,
                    'total_chunks': total_chunks,
                    'processing_complete': actual_chunk_count >= total_chunks,
                    'remaining_topics_queued': len(remaining_document_ids)
                }
                
                # Create user-friendly message
                if len(chunks) > initial_batch_size:
                    message = f"Topic {first_topic} initial processing complete with {actual_chunk_count} chunks. " + \
                            f"Remaining {total_chunks - actual_chunk_count} chunks will be processed in the background."
                    
                    if remaining_document_ids:
                        message += f" {len(remaining_document_ids)} additional topics queued for background processing."
                else:
                    message = f"Topic {first_topic} fully processed with {actual_chunk_count} chunks."
                    
                    if remaining_document_ids:
                        message += f" {len(remaining_document_ids)} additional topics queued for background processing."
                
                response_data['message'] = message
                
                return jsonify(response_data)
                
            except Exception as content_error:
                logger.exception(f"Error processing content for {first_topic}: {str(content_error)}")
                return jsonify({
                    'success': False,
                    'message': f'Error processing content: {str(content_error)}'
                }), 500
                
        except Exception as doc_error:
            logger.exception(f"Error creating document: {str(doc_error)}")
            return jsonify({
                'success': False,
                'message': f'Error creating document: {str(doc_error)}'
            }), 500
            
    except Exception as e:
        logger.exception(f"Error processing topic pages: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error processing topic pages: {str(e)}'
        }), 500