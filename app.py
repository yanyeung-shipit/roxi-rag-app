import os
import logging
import tempfile
import datetime
import urllib.parse
import json
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, abort
from werkzeug.utils import secure_filename
from werkzeug.security import safe_join
from utils.document_processor import process_pdf
from utils.web_scraper import scrape_website, create_minimal_content_for_topic
from utils.vector_store import VectorStore
from utils.llm_service import generate_response
from models import db, Document, DocumentChunk, Collection

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")

# Configure database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# Improve connection pool settings to handle connection timeouts
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,  # Test connections before use to avoid stale connections
    "pool_recycle": 280,    # Recycle connections after 280 seconds (before default 5-min timeout)
    "pool_timeout": 30,     # Maximum time to wait for connection from pool
    "pool_size": 10,        # Maximum number of connections to keep persistently
    "max_overflow": 20      # Maximum number of connections to create above pool_size
}
db.init_app(app)

# Create uploads directory if it doesn't exist
UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20MB limit

# Initialize vector store
vector_store = VectorStore()

# Configure upload settings
ALLOWED_EXTENSIONS = {'pdf'}
TEMP_FOLDER = tempfile.gettempdir()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/manage')
def manage():
    """Document management interface."""
    return render_template('manage.html')

@app.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    """Process and store PDF data. This version is optimized and saves to database."""
    try:
        # Check if file part exists
        if 'pdf_file' not in request.files:
            logger.warning("No file part in the request")
            return jsonify({
                'success': False, 
                'message': 'No file part in the request'
            }), 400
        
        file = request.files['pdf_file']
        
        # Check if file was selected
        if file.filename == '':
            logger.warning("No file selected")
            return jsonify({
                'success': False, 
                'message': 'No file selected'
            }), 400
        
        # Process valid file
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            logger.info(f"Processing PDF: {filename}")
            
            # Check file size before saving - reduce to 20MB max
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)  # Reset file pointer
            
            if file_size > 20 * 1024 * 1024:  # 20MB limit
                logger.warning(f"PDF file too large: {file_size / (1024*1024):.2f} MB")
                return jsonify({
                    'success': False, 
                    'message': f'PDF file too large ({file_size / (1024*1024):.2f} MB). Maximum size is 20 MB.'
                }), 400
            
            # Save file to permanent storage in uploads folder
            # Create a unique filename to avoid overwriting
            # Use timestamp and original filename
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            unique_filename = f"{timestamp}_{filename}"
            file_path = safe_join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(file_path)
            logger.debug(f"Saved file to {file_path}")
            
            # Create a new document record in the database
            new_document = Document(
                filename=filename,
                title=filename,  # We can update this later with better metadata
                file_type="pdf",
                file_path=file_path,
                file_size=file_size,
                processed=False  # Mark as unprocessed initially
            )
            
            db.session.add(new_document)
            db.session.commit()
            logger.info(f"Created document record with ID: {new_document.id}")
            
            try:
                # Process PDF and add to vector store
                chunks = process_pdf(file_path, filename)
                
                if not chunks:
                    logger.warning("No chunks extracted from PDF")
                    return jsonify({
                        'success': False, 
                        'message': 'Could not extract any text from the PDF. The file may be scanned images or protected.'
                    }), 400
                    
                logger.info(f"Successfully processed PDF with {len(chunks)} chunks")
                
                # Update document with page count if available
                if chunks and 'page_count' in chunks[0]['metadata']:
                    new_document.page_count = chunks[0]['metadata']['page_count']
                    db.session.commit()
                    logger.debug(f"Updated document with page count: {new_document.page_count}")
                
                # Further limit chunks to prevent memory issues
                max_chunks = 50
                if len(chunks) > max_chunks:
                    logger.warning(f"Limiting {len(chunks)} chunks to first {max_chunks}")
                    chunks = chunks[:max_chunks]
                
                # Save chunks in smaller batches to prevent timeouts
                batch_size = 10
                total_batches = (len(chunks) + batch_size - 1) // batch_size
                
                success_count = 0
                chunk_records = []
                
                try:
                    for i in range(0, len(chunks), batch_size):
                        batch = chunks[i:i + batch_size]
                        logger.debug(f"Processing batch {(i // batch_size) + 1}/{total_batches} with {len(batch)} chunks")
                        
                        # Process each chunk with error handling
                        for chunk_index, chunk in enumerate(batch):
                            try:
                                # Add to vector store
                                vector_store.add_text(chunk['text'], chunk['metadata'])
                                
                                # Create database record for this chunk
                                chunk_record = DocumentChunk(
                                    document_id=new_document.id,
                                    chunk_index=i + chunk_index,
                                    page_number=chunk['metadata'].get('page', None),
                                    text_content=chunk['text']
                                )
                                chunk_records.append(chunk_record)
                                success_count += 1
                            except Exception as chunk_error:
                                logger.warning(f"Error adding chunk to vector store: {str(chunk_error)}")
                                # Continue with next chunk
                        
                        # Save vector store after each batch
                        try:
                            vector_store._save()
                            logger.debug(f"Saved vector store after batch {(i // batch_size) + 1}")
                            
                            # Commit chunk records to database in batches
                            if chunk_records:
                                db.session.add_all(chunk_records)
                                db.session.commit()
                                logger.debug(f"Saved {len(chunk_records)} chunk records to database")
                                chunk_records = []  # Clear for next batch
                                
                        except Exception as save_error:
                            logger.warning(f"Error saving batch: {str(save_error)}")
                            # Continue processing
                            
                except Exception as batch_error:
                    logger.exception(f"Error processing batch: {str(batch_error)}")
                    # Continue to mark document as processed and return partial success
                finally:
                    # Mark document as processed if any chunks were successful
                    if success_count > 0:
                        new_document.processed = True
                        db.session.commit()
                        logger.debug("Document marked as processed")
                
                # Return success even if only some chunks were processed
                if success_count > 0:
                    return jsonify({
                        'success': True, 
                        'message': f'Successfully processed {filename} ({success_count} of {len(chunks)} chunks)',
                        'document_id': new_document.id,
                        'chunks': success_count
                    })
                else:
                    # Document processing failed, but file was saved
                    return jsonify({
                        'success': False, 
                        'message': 'File was saved but could not add any content to the knowledge base.'
                    }), 500
                    
            except Exception as processing_error:
                logger.exception(f"Error processing PDF: {str(processing_error)}")
                # Keep the file but mark processing as failed
                return jsonify({
                    'success': False, 
                    'message': f'Error processing PDF: {str(processing_error)}'
                }), 500
        else:
            logger.warning(f"Invalid file type: {file.filename}")
            return jsonify({
                'success': False, 
                'message': 'Invalid file type. Only PDF files are allowed.'
            }), 400
    except Exception as e:
        logger.exception(f"Error processing PDF: {str(e)}")
        return jsonify({
            'success': False, 
            'message': f'Error processing PDF: {str(e)}'
        }), 500

@app.route('/add_website', methods=['POST'])
def add_website():
    """Process and store website data with multi-page crawling."""
    try:
        data = request.form
        url = data.get('website_url', '')
        
        if not url:
            logger.warning("No URL provided")
            return jsonify({
                'success': False, 
                'message': 'URL is required'
            }), 400
        
        logger.info(f"Processing website with multi-page crawling: {url}")
        
        # Special handling for rheum.reviews domain - check if we should add multiple topics
        if 'rheum.reviews' in url and not any(pattern in url for pattern in ['/topic/', '/disease/', '/condition/']):
            # If it's the homepage or a non-topic page, we might want to suggest specific topic pages instead
            return jsonify({
                'success': False,
                'message': 'For rheum.reviews, it\'s better to add specific topic pages directly. For example: https://rheum.reviews/topic/myositis/, https://rheum.reviews/topic/scleroderma/, etc.'
            }), 400
        
        # Create a new document record in the database
        new_document = Document(
            filename=url,  # Use URL as filename
            title=url,     # Will update with proper title after scraping
            file_type="website",
            source_url=url,
            processed=False  # Mark as unprocessed initially
        )
        
        db.session.add(new_document)
        db.session.commit()
        logger.info(f"Created document record with ID: {new_document.id}")
        
        # Check if URL appears to be a specific topic/disease page
        is_topic_page = False
        topic_patterns = ['/topic/', '/disease/', '/diseases/', '/condition/', '/conditions/']
        parsed_url = urllib.parse.urlparse(url)
        if any(pattern in parsed_url.path for pattern in topic_patterns):
            is_topic_page = True
            logger.info(f"Detected specific topic URL: {url} - this will be given special priority")
            
        # Scrape website with multi-page crawling
        try:
            # Handle topic pages differently to avoid memory issues
            if is_topic_page:
                logger.debug(f"Processing single topic page: {url}")
                # For topic pages, we prioritize direct content extraction over crawling
                # This avoids memory issues while still getting the important content
                chunks = scrape_website(url, max_pages=5, max_wait_time=90)  # Very limited crawling for topic pages
            elif '/rheum.reviews/' in url:
                # For rheum.reviews domain, be very conservative to avoid memory issues
                logger.debug(f"Starting limited rheum.reviews crawl from: {url}")
                chunks = scrape_website(url, max_pages=5, max_wait_time=90)  # More conservative for this specific site
            else:
                logger.debug(f"Starting standard multi-page crawl from: {url}")
                # Use the enhanced multi-page crawler with reasonable limits
                chunks = scrape_website(url, max_pages=12, max_wait_time=90)  # Balanced approach
                
            logger.debug(f"Crawled website with {len(chunks) if chunks else 0} chunks from multiple pages")
            
            if not chunks:
                logger.warning(f"No content extracted from website: {url}")
                # Document exists but processing failed
                return jsonify({
                    'success': False, 
                    'message': 'Could not extract any content from the provided URL or its linked pages'
                }), 400
        except Exception as scrape_error:
            logger.exception(f"Error crawling website: {str(scrape_error)}")
            return jsonify({
                'success': False, 
                'message': f'Error crawling website: {str(scrape_error)}'
            }), 500
            
        # Update document with title from the first page
        if chunks and 'title' in chunks[0]['metadata']:
            new_document.title = chunks[0]['metadata']['title']
            db.session.commit()
            logger.debug(f"Updated document with title: {new_document.title}")
            
        logger.info(f"Successfully crawled website with {len(chunks)} chunks from multiple pages")
        
        # Limit chunks to prevent memory issues
        max_chunks = 200  # Increased from 150 to 200 to better cover multi-page websites
        if len(chunks) > max_chunks:
            logger.warning(f"Limiting {len(chunks)} chunks to first {max_chunks}")
            chunks = chunks[:max_chunks]
        
        # Process chunks in smaller batches to prevent timeouts
        batch_size = 10
        total_batches = (len(chunks) + batch_size - 1) // batch_size
        
        success_count = 0
        chunk_records = []
        
        # Track unique URLs processed
        processed_urls = set()
        for chunk in chunks:
            if 'url' in chunk['metadata']:
                processed_urls.add(chunk['metadata']['url'])
        
        logger.info(f"Processing chunks from {len(processed_urls)} unique URLs")
        
        try:
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i + batch_size]
                logger.debug(f"Processing batch {(i // batch_size) + 1}/{total_batches} with {len(batch)} chunks")
                
                # Process each chunk with error handling
                for chunk_index, chunk in enumerate(batch):
                    try:
                        # Add additional metadata for debugging
                        chunk['metadata']['document_id'] = new_document.id
                        
                        # Add to vector store
                        vector_store.add_text(chunk['text'], chunk['metadata'])
                        
                        # Create database record for this chunk
                        chunk_record = DocumentChunk(
                            document_id=new_document.id,
                            chunk_index=i + chunk_index,
                            page_number=chunk['metadata'].get('page_number', None),  # Store page number if available
                            text_content=chunk['text']
                        )
                        chunk_records.append(chunk_record)
                        success_count += 1
                    except Exception as chunk_error:
                        logger.warning(f"Error adding chunk to vector store: {str(chunk_error)}")
                        # Continue with next chunk
                
                # Save vector store after each batch
                try:
                    vector_store._save()
                    logger.debug(f"Saved vector store after batch {(i // batch_size) + 1}")
                    
                    # Commit chunk records to database in batches
                    if chunk_records:
                        db.session.add_all(chunk_records)
                        db.session.commit()
                        logger.debug(f"Saved {len(chunk_records)} chunk records to database")
                        chunk_records = []  # Clear for next batch
                except Exception as save_error:
                    logger.warning(f"Error saving batch: {str(save_error)}")
                    # Continue processing
                    
        except Exception as batch_error:
            logger.exception(f"Error processing batch: {str(batch_error)}")
            # Continue to mark document as processed and return partial success
        finally:
            # Mark document as processed if any chunks were successful
            if success_count > 0:
                new_document.processed = True
                db.session.commit()
                logger.debug("Document marked as processed")
        
        # Return success even if only some chunks were processed
        if success_count > 0:
            return jsonify({
                'success': True, 
                'message': f'Successfully processed website: {url} ({success_count} chunks from {len(processed_urls)} pages)',
                'document_id': new_document.id,
                'chunks': success_count,
                'pages': len(processed_urls)
            })
        else:
            return jsonify({
                'success': False, 
                'message': 'Could not add any content from the website to the knowledge base.'
            }), 500
            
    except Exception as e:
        logger.exception(f"Error processing website: {str(e)}")
        return jsonify({
            'success': False, 
            'message': f'Error processing website: {str(e)}'
        }), 500

@app.route('/query', methods=['POST'])
def query():
    try:
        data = request.form
        query_text = data.get('query', '')
        
        if not query_text:
            return jsonify({
                'success': False, 
                'message': 'Query is required'
            }), 400
        
        # Get similar documents from vector store
        retrieval_results = vector_store.search(query_text, top_k=5)
        
        if not retrieval_results:
            return jsonify({
                'success': True,
                'answer': "ROXI doesn't have enough information in the rheumatology knowledge base to answer this question based on the documents you've provided.",
                'sources': []
            })
            
        # Debug log the retrieval results
        logger.debug(f"Retrieved {len(retrieval_results)} documents for query: {query_text[:50]}...")
        
        # Log source types for debugging
        source_types = {}
        for doc in retrieval_results:
            source_type = doc.get('metadata', {}).get('source_type', 'unknown')
            source_types[source_type] = source_types.get(source_type, 0) + 1
            
            # Log individual source details
            if source_type == 'website':
                url = doc.get('metadata', {}).get('url', 'unknown')
                title = doc.get('metadata', {}).get('title', 'unknown')
                logger.debug(f"Website source: {title} - {url}")
                
        logger.info(f"Source types for query '{query_text[:30]}...': {source_types}")
        
        # Generate response using LLM
        answer, sources = generate_response(query_text, retrieval_results)
        
        return jsonify({
            'success': True,
            'answer': answer,
            'sources': sources
        })
    except Exception as e:
        logger.exception("Error processing query")
        return jsonify({
            'success': False, 
            'message': f'Error processing query: {str(e)}'
        }), 500

@app.route('/stats', methods=['GET'])
def stats():
    try:
        # Get vector store stats
        vector_stats = vector_store.get_stats()
        
        # Get database stats
        db_stats = {
            'total_documents': Document.query.count(),
            'pdfs': Document.query.filter_by(file_type='pdf').count(),
            'websites': Document.query.filter_by(file_type='website').count(),
            'chunks': DocumentChunk.query.count(),
            'collections': Collection.query.count()
        }
        
        # Combine stats with precedence to database (more accurate)
        combined_stats = {
            'total_documents': db_stats['total_documents'] or vector_stats['total_documents'],
            'pdfs': db_stats['pdfs'] or vector_stats['pdfs'],
            'websites': db_stats['websites'] or vector_stats['websites'],
            'chunks': db_stats['chunks'] or vector_stats['chunks'],
            'collections': db_stats['collections']
        }
        
        return jsonify({
            'success': True,
            'stats': combined_stats
        })
    except Exception as e:
        logger.exception("Error retrieving stats")
        return jsonify({
            'success': False, 
            'message': f'Error retrieving stats: {str(e)}'
        }), 500

@app.route('/clear', methods=['POST'])
def clear():
    try:
        vector_store.clear()
        
        # Optionally also clear database tables
        if request.form.get('clear_database', 'false').lower() == 'true':
            # Delete all document chunks first (due to foreign key constraint)
            DocumentChunk.query.delete()
            # Delete all documents
            Document.query.delete()
            # Delete all collections
            Collection.query.delete()
            db.session.commit()
            logger.info("Cleared all database records")
            
        return jsonify({
            'success': True,
            'message': 'Knowledge base cleared successfully'
        })
    except Exception as e:
        logger.exception("Error clearing knowledge base")
        return jsonify({
            'success': False, 
            'message': f'Error clearing knowledge base: {str(e)}'
        }), 500
        
# New endpoint specifically for adding multiple rheum.reviews topic pages at once
@app.route('/add_topic_pages', methods=['POST'])
def add_topic_pages():
    """Add multiple rheum.reviews topic pages at once. Memory-optimized version."""
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
        
        # MEMORY OPTIMIZATION: Reduce maximum number of topics to 2
        max_topics = 2
        if len(topics) > max_topics:
            topics = topics[:max_topics]  # Silently truncate to reduce memory issues
            logger.warning(f"Limiting to first {max_topics} topics to prevent memory issues")
        
        # Format topic URLs
        base_url = "https://rheum.reviews/topic/"
        processed_topics = []
        failed_topics = []
        
        # Process one topic at a time to reduce memory pressure
        for topic in topics:
            # Reset variables to help with memory cleanup
            chunks = None
            chunk_records = []
            
            # Clean the topic name for URL
            topic_slug = topic.strip().lower().replace(' ', '-')
            if not topic_slug:
                failed_topics.append({"topic": topic, "reason": "Invalid topic name"})
                continue
                
            url = f"{base_url}{topic_slug}/"
            
            try:
                # Create a new document record in the database
                new_document = Document(
                    filename=url,
                    title=f"Topic: {topic}",  # Will update with proper title after scraping
                    file_type="website",
                    source_url=url,
                    processed=False
                )
                
                db.session.add(new_document)
                db.session.commit()
                
                # Process the topic page with strict limits to avoid memory issues
                logger.info(f"Processing topic page with memory optimization: {url}")
                try:
                    # Use memory-optimized content fetching for topic pages 
                    chunks = create_minimal_content_for_topic(url)
                    
                    # Don't even try crawling to avoid memory issues
                    if not chunks:
                        logger.warning(f"Memory-optimized content extraction failed for {url}")
                        raise Exception("Could not extract content from topic page")
                    
                except Exception as e:
                    logger.error(f"Error processing topic {topic}: {str(e)}")
                    failed_topics.append({"topic": topic, "reason": f"Error: {str(e)}"})
                    
                    # Clean up any partial document
                    try:
                        db.session.delete(new_document)
                        db.session.commit()
                    except Exception:
                        pass
                    
                    continue
                
                if not chunks or len(chunks) == 0:
                    failed_topics.append({"topic": topic, "reason": "No content extracted"})
                    
                    # Clean up any partial document
                    try:
                        db.session.delete(new_document)
                        db.session.commit()
                    except Exception:
                        pass
                    
                    continue
                
                # Update document with title
                if 'title' in chunks[0]['metadata']:
                    new_document.title = chunks[0]['metadata']['title']
                    db.session.commit()
                
                # MEMORY OPTIMIZATION: Dynamic chunk limits based on topic importance
                
                # Check if this is a priority topic (important rheumatology conditions)
                priority_topics = ['rheumatoid-arthritis', 'lupus', 'systemic-sclerosis', 
                                  'vasculitis', 'myositis', 'spondyloarthritis']
                
                is_priority = any(pt in topic_slug for pt in priority_topics)
                
                # Set chunk limit based on priority and whether this is a single topic request
                if is_priority:
                    if len(topics) == 1:
                        # For single priority topics, allow more chunks
                        max_chunks = 15
                        logger.info(f"Single priority topic requested: {topic}, allowing {max_chunks} chunks")
                    else:
                        # For multiple topics including at least one priority topic
                        max_chunks = 10
                        logger.info(f"Priority topic in batch: {topic}, allowing {max_chunks} chunks")
                else:
                    if len(topics) == 1:
                        # For single regular topics
                        max_chunks = 8
                    else:
                        # For multiple regular topics
                        max_chunks = 5
                
                # Store the original number of chunks for later use
                original_chunk_count = len(chunks)
                
                # Apply the limit
                if len(chunks) > max_chunks:
                    logger.warning(f"Limiting chunks from {original_chunk_count} to {max_chunks} for memory optimization")
                    
                    # Store metadata about remaining chunks for later loading
                    if original_chunk_count > max_chunks:
                        # Add a special flag to the database record to indicate more content is available
                        new_document.file_size = original_chunk_count  # Repurpose file_size to store total chunk count
                        db.session.commit()
                    
                    chunks = chunks[:max_chunks]
                
                success_count = 0
                
                # Process chunks one at a time with explicit database commits
                for i, chunk in enumerate(chunks):
                    try:
                        # Add to vector store
                        vector_store.add_text(chunk['text'], chunk['metadata'])
                        
                        # Create and immediately save database record to minimize memory usage
                        chunk_record = DocumentChunk(
                            document_id=new_document.id,
                            chunk_index=i,
                            page_number=chunk['metadata'].get('page_number', 1),
                            text_content=chunk['text']
                        )
                        
                        db.session.add(chunk_record)
                        db.session.commit()
                        
                        success_count += 1
                        
                        # Save vector store after each chunk to prevent memory buildup
                        vector_store._save()
                        
                    except Exception as e:
                        logger.error(f"Error processing chunk {i} for topic {topic}: {str(e)}")
                        # Continue processing next chunk
                
                # Mark document as processed if any chunks were successful
                if success_count > 0:
                    new_document.processed = True
                    db.session.commit()
                    processed_topics.append({
                        "topic": topic,
                        "url": url,
                        "chunks": success_count,
                        "document_id": new_document.id
                    })
                else:
                    failed_topics.append({"topic": topic, "reason": "Failed to add chunks to database"})
                    
                    # Clean up any partial document
                    try:
                        db.session.delete(new_document)
                        db.session.commit()
                    except Exception:
                        pass
                
                # Explicitly clean up memory
                chunks = None
                chunk_records = []
                
            except Exception as e:
                logger.exception(f"Error processing topic {topic}: {str(e)}")
                failed_topics.append({"topic": topic, "reason": str(e)})
            
            # Force Python garbage collection to free memory
            import gc
            gc.collect()
        
        if processed_topics:
            return jsonify({
                'success': True,
                'message': f'Successfully processed {len(processed_topics)} topic pages with memory optimization',
                'processed': processed_topics,
                'failed': failed_topics
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to process any topic pages. Try with fewer topics (1-2 max).',
                'failed': failed_topics
            }), 500
            
    except Exception as e:
        logger.exception(f"Error processing topic pages: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error processing topic pages: {str(e)}'
        }), 500

# New endpoints for database operations

@app.route('/documents', methods=['GET'])
def get_documents():
    """Get a list of all documents."""
    try:
        documents = Document.query.all()
        results = []
        
        for doc in documents:
            results.append({
                'id': doc.id,
                'title': doc.title,
                'filename': doc.filename,
                'file_type': doc.file_type,
                'source_url': doc.source_url,
                'file_path': doc.file_path,
                'file_size': doc.file_size,
                'page_count': doc.page_count,
                'created_at': doc.created_at.isoformat() if doc.created_at else None,
                'processed': doc.processed,
                'chunk_count': len(doc.chunks)
            })
            
        return jsonify({
            'success': True,
            'documents': results
        })
    except Exception as e:
        logger.exception("Error retrieving documents")
        return jsonify({
            'success': False, 
            'message': f'Error retrieving documents: {str(e)}'
        }), 500

@app.route('/documents/<int:document_id>', methods=['GET'])
def get_document(document_id):
    """Get details of a specific document."""
    try:
        doc = Document.query.get(document_id)
        
        if not doc:
            return jsonify({
                'success': False,
                'message': f'Document with ID {document_id} not found'
            }), 404
            
        chunks = []
        for chunk in doc.chunks:
            chunks.append({
                'id': chunk.id,
                'chunk_index': chunk.chunk_index,
                'page_number': chunk.page_number,
                'text_content': chunk.text_content[:100] + '...' if len(chunk.text_content) > 100 else chunk.text_content
            })
            
        result = {
            'id': doc.id,
            'title': doc.title,
            'filename': doc.filename,
            'file_type': doc.file_type,
            'source_url': doc.source_url,
            'file_path': doc.file_path,
            'file_size': doc.file_size,
            'page_count': doc.page_count,
            'created_at': doc.created_at.isoformat() if doc.created_at else None,
            'processed': doc.processed,
            'chunks': chunks
        }
            
        return jsonify({
            'success': True,
            'document': result
        })
    except Exception as e:
        logger.exception(f"Error retrieving document {document_id}")
        return jsonify({
            'success': False, 
            'message': f'Error retrieving document: {str(e)}'
        }), 500

@app.route('/documents/<int:document_id>/load_more_content', methods=['POST'])
def load_more_document_content(document_id):
    """Load more content for a document that has additional chunks available."""
    try:
        # Find the document
        doc = Document.query.get(document_id)
        
        if not doc:
            return jsonify({
                'success': False,
                'message': f'Document with ID {document_id} not found'
            }), 404
        
        # Check if this is a website document (only website docs support this feature)
        if doc.file_type != 'website':
            return jsonify({
                'success': False,
                'message': 'This operation is only supported for website documents'
            }), 400
        
        # Check if there's more content to load by looking at file_size (repurposed to store total chunk count)
        current_chunk_count = len(doc.chunks)
        total_possible_chunks = doc.file_size or 0
        
        # If there's no more content or file_size wasn't set properly
        if total_possible_chunks <= current_chunk_count or total_possible_chunks <= 0:
            return jsonify({
                'success': False,
                'message': 'No additional content available for this document'
            }), 400
        
        # Get the document URL
        url = doc.source_url
        if not url:
            return jsonify({
                'success': False,
                'message': 'Document has no source URL to load additional content'
            }), 400
        
        # Determine how many more chunks to load (maximum 5 more at a time)
        chunks_to_load = min(5, total_possible_chunks - current_chunk_count)
        
        logger.info(f"Attempting to load {chunks_to_load} more chunks for document {document_id}")
        
        # Extract the topic name from the URL for crawling parameters
        parsed_url = urllib.parse.urlparse(url)
        path_parts = parsed_url.path.strip('/').split('/')
        topic_slug = path_parts[-1] if path_parts else ""
        
        try:
            # Get fresh content to ensure we have all chunks
            chunks = create_minimal_content_for_topic(url)
            
            if not chunks:
                return jsonify({
                    'success': False,
                    'message': 'Failed to retrieve additional content'
                }), 500
            
            # Skip chunks we already have and take only the next batch
            start_index = current_chunk_count
            end_index = min(start_index + chunks_to_load, len(chunks))
            
            if start_index >= len(chunks):
                return jsonify({
                    'success': False,
                    'message': 'No additional content available'
                }), 400
            
            chunks_to_add = chunks[start_index:end_index]
            added_count = 0
            
            # Process each additional chunk
            for i, chunk in enumerate(chunks_to_add):
                try:
                    # Update chunk index to continue from existing chunks
                    chunk_index = current_chunk_count + i
                    
                    # Update metadata to reflect new chunk index
                    chunk['metadata']['chunk_index'] = chunk_index
                    
                    # Add to vector store
                    vector_store.add_text(chunk['text'], chunk['metadata'])
                    
                    # Create database record
                    chunk_record = DocumentChunk(
                        document_id=doc.id,
                        chunk_index=chunk_index,
                        page_number=chunk['metadata'].get('page_number', 1),
                        text_content=chunk['text']
                    )
                    
                    db.session.add(chunk_record)
                    db.session.commit()
                    
                    # Save vector store after each chunk
                    vector_store._save()
                    
                    added_count += 1
                except Exception as e:
                    logger.error(f"Error adding chunk {i+start_index}: {str(e)}")
            
            # Update total loaded count
            new_total = current_chunk_count + added_count
            
            # Return results
            return jsonify({
                'success': True,
                'message': f'Added {added_count} more chunks to document',
                'document_id': document_id,
                'chunks_loaded': added_count,
                'total_chunks_now': new_total,
                'total_possible_chunks': total_possible_chunks,
                'has_more': new_total < total_possible_chunks
            })
            
        except Exception as e:
            logger.exception(f"Error loading additional content: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'Error loading additional content: {str(e)}'
            }), 500
    
    except Exception as e:
        logger.exception(f"Error processing request: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

@app.route('/documents/<int:document_id>', methods=['DELETE'])
def delete_document(document_id):
    """Delete a specific document and its chunks."""
    try:
        doc = Document.query.get(document_id)
        
        if not doc:
            return jsonify({
                'success': False,
                'message': f'Document with ID {document_id} not found'
            }), 404
            
        # Need to update vector store too, but this is complex
        # For now, just delete from database
        
        # Delete all chunks first
        DocumentChunk.query.filter_by(document_id=document_id).delete()
        
        # Save the filename for reporting
        filename = doc.filename
        
        # Delete the document
        db.session.delete(doc)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Document "{filename}" (ID: {document_id}) deleted successfully'
        })
    except Exception as e:
        logger.exception(f"Error deleting document {document_id}")
        return jsonify({
            'success': False, 
            'message': f'Error deleting document: {str(e)}'
        }), 500

@app.route('/collections', methods=['GET'])
def get_collections():
    """Get a list of all collections."""
    try:
        collections = Collection.query.all()
        results = []
        
        for coll in collections:
            results.append({
                'id': coll.id,
                'name': coll.name,
                'description': coll.description,
                'created_at': coll.created_at.isoformat() if coll.created_at else None,
                'document_count': len(coll.documents)
            })
            
        return jsonify({
            'success': True,
            'collections': results
        })
    except Exception as e:
        logger.exception("Error retrieving collections")
        return jsonify({
            'success': False, 
            'message': f'Error retrieving collections: {str(e)}'
        }), 500

@app.route('/collections', methods=['POST'])
def create_collection():
    """Create a new collection."""
    try:
        logger.debug(f"Collection creation request received: {request.get_data(as_text=True)}")
        
        # Check content type
        if request.content_type != 'application/json':
            logger.warning(f"Incorrect content type: {request.content_type}")
            return jsonify({
                'success': False,
                'message': 'Content-Type must be application/json'
            }), 400
        
        data = request.json
        logger.debug(f"Parsed JSON data: {data}")
        
        if not data or 'name' not in data:
            logger.warning("Name is missing from the request")
            return jsonify({
                'success': False,
                'message': 'Collection name is required'
            }), 400
            
        name = data.get('name')
        description = data.get('description', '')
        
        logger.info(f"Creating collection with name: '{name}', description: '{description}'")
        
        # Check if collection with this name already exists
        existing = Collection.query.filter_by(name=name).first()
        if existing:
            logger.warning(f"Collection with name '{name}' already exists")
            return jsonify({
                'success': False,
                'message': f'Collection with name "{name}" already exists'
            }), 400
        
        # Create new collection
        new_collection = Collection(
            name=name,
            description=description
        )
        
        db.session.add(new_collection)
        db.session.commit()
        
        logger.info(f"Collection created successfully with ID: {new_collection.id}")
        
        return jsonify({
            'success': True,
            'message': f'Collection "{name}" created successfully',
            'collection_id': new_collection.id
        })
    except Exception as e:
        logger.exception(f"Error creating collection: {str(e)}")
        return jsonify({
            'success': False, 
            'message': f'Error creating collection: {str(e)}'
        }), 500

@app.route('/collections/<int:collection_id>/documents', methods=['POST'])
def add_document_to_collection(collection_id):
    """Add a document to a collection."""
    try:
        data = request.json
        
        if not data or 'document_id' not in data:
            return jsonify({
                'success': False,
                'message': 'Document ID is required'
            }), 400
            
        document_id = data.get('document_id')
        
        # Check if collection exists
        collection = Collection.query.get(collection_id)
        if not collection:
            return jsonify({
                'success': False,
                'message': f'Collection with ID {collection_id} not found'
            }), 404
            
        # Check if document exists
        document = Document.query.get(document_id)
        if not document:
            return jsonify({
                'success': False,
                'message': f'Document with ID {document_id} not found'
            }), 404
            
        # Check if document is already in the collection
        if document in collection.documents:
            return jsonify({
                'success': False,
                'message': f'Document with ID {document_id} is already in collection "{collection.name}"'
            }), 400
            
        # Add document to collection
        collection.documents.append(document)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Document "{document.title}" added to collection "{collection.name}"'
        })
    except Exception as e:
        logger.exception(f"Error adding document to collection {collection_id}")
        return jsonify({
            'success': False, 
            'message': f'Error adding document to collection: {str(e)}'
        }), 500

@app.route('/collections/<int:collection_id>', methods=['GET'])
def get_collection(collection_id):
    """Get details of a specific collection."""
    try:
        collection = Collection.query.get(collection_id)
        
        if not collection:
            return jsonify({
                'success': False,
                'message': f'Collection with ID {collection_id} not found'
            }), 404
            
        # Get documents in this collection
        documents = []
        for doc in collection.documents:
            documents.append({
                'id': doc.id,
                'title': doc.title,
                'filename': doc.filename,
                'file_type': doc.file_type,
                'created_at': doc.created_at.isoformat() if doc.created_at else None
            })
            
        result = {
            'id': collection.id,
            'name': collection.name,
            'description': collection.description,
            'created_at': collection.created_at.isoformat() if collection.created_at else None,
            'updated_at': collection.updated_at.isoformat() if collection.updated_at else None,
            'documents': documents
        }
        
        return jsonify({
            'success': True,
            'collection': result
        })
    except Exception as e:
        logger.exception(f"Error retrieving collection {collection_id}")
        return jsonify({
            'success': False, 
            'message': f'Error retrieving collection: {str(e)}'
        }), 500

@app.route('/collections/<int:collection_id>', methods=['PUT'])
def update_collection(collection_id):
    """Update a collection."""
    try:
        logger.debug(f"Collection update request for ID {collection_id}: {request.get_data(as_text=True)}")
        
        # Check content type
        if request.content_type != 'application/json':
            logger.warning(f"Incorrect content type: {request.content_type}")
            return jsonify({
                'success': False,
                'message': 'Content-Type must be application/json'
            }), 400
        
        data = request.json
        logger.debug(f"Parsed JSON data: {data}")
        
        if not data:
            logger.warning("No data provided in the request")
            return jsonify({
                'success': False,
                'message': 'No update data provided'
            }), 400
            
        # Check if collection exists
        collection = Collection.query.get(collection_id)
        if not collection:
            logger.warning(f"Collection with ID {collection_id} not found")
            return jsonify({
                'success': False,
                'message': f'Collection with ID {collection_id} not found'
            }), 404
            
        # Update collection fields
        if 'name' in data:
            # Check if name is already taken by another collection
            existing = Collection.query.filter(Collection.name == data['name'], Collection.id != collection_id).first()
            if existing:
                logger.warning(f"Collection with name '{data['name']}' already exists")
                return jsonify({
                    'success': False,
                    'message': f'Collection with name "{data["name"]}" already exists'
                }), 400
                
            collection.name = data['name']
            
        if 'description' in data:
            collection.description = data['description']
            
        # Update the updated_at timestamp
        collection.updated_at = datetime.datetime.now(datetime.timezone.utc)
        
        db.session.commit()
        
        logger.info(f"Collection {collection_id} updated successfully")
        
        return jsonify({
            'success': True,
            'message': f'Collection updated successfully',
            'collection_id': collection.id
        })
    except Exception as e:
        logger.exception(f"Error updating collection {collection_id}: {str(e)}")
        return jsonify({
            'success': False, 
            'message': f'Error updating collection: {str(e)}'
        }), 500

@app.route('/collections/<int:collection_id>', methods=['DELETE'])
def delete_collection(collection_id):
    """Delete a collection."""
    try:
        # Check if collection exists
        collection = Collection.query.get(collection_id)
        if not collection:
            return jsonify({
                'success': False,
                'message': f'Collection with ID {collection_id} not found'
            }), 404
            
        # Store name for response message
        collection_name = collection.name
            
        # Delete the collection
        db.session.delete(collection)
        db.session.commit()
        
        logger.info(f"Collection {collection_id} '{collection_name}' deleted successfully")
        
        return jsonify({
            'success': True,
            'message': f'Collection "{collection_name}" deleted successfully'
        })
    except Exception as e:
        logger.exception(f"Error deleting collection {collection_id}")
        return jsonify({
            'success': False, 
            'message': f'Error deleting collection: {str(e)}'
        }), 500
