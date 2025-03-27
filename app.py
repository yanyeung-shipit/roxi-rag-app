import os
import logging
import tempfile
import datetime
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
from werkzeug.utils import secure_filename
from werkzeug.security import safe_join
from utils.document_processor import process_pdf
from utils.web_scraper import scrape_website
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
    """Process and store website data. Using optimized batch processing and saving to database."""
    try:
        data = request.form
        url = data.get('website_url', '')
        
        if not url:
            logger.warning("No URL provided")
            return jsonify({
                'success': False, 
                'message': 'URL is required'
            }), 400
        
        logger.info(f"Processing website: {url}")
        
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
        
        # Scrape website and add to vector store
        chunks = scrape_website(url)
        
        if not chunks:
            logger.warning(f"No content extracted from website: {url}")
            # Document exists but processing failed
            return jsonify({
                'success': False, 
                'message': 'Could not extract any content from the provided URL'
            }), 400
            
        # Update document with title if available
        if chunks and 'title' in chunks[0]['metadata']:
            new_document.title = chunks[0]['metadata']['title']
            db.session.commit()
            logger.debug(f"Updated document with title: {new_document.title}")
            
        logger.info(f"Successfully scraped website with {len(chunks)} chunks")
        
        # Limit chunks to prevent memory issues
        max_chunks = 50
        if len(chunks) > max_chunks:
            logger.warning(f"Limiting {len(chunks)} chunks to first {max_chunks}")
            chunks = chunks[:max_chunks]
        
        # Process chunks in smaller batches to prevent timeouts
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
                'message': f'Successfully processed website: {url} ({success_count} of {len(chunks)} chunks)',
                'document_id': new_document.id,
                'chunks': success_count
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
                'answer': "I don't have enough information to answer this question based on the documents you've provided.",
                'sources': []
            })
            
        # Debug log the retrieval results
        logger.debug(f"Retrieved {len(retrieval_results)} documents for query: {query_text[:50]}...")
        
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
        data = request.json
        
        if not data or 'name' not in data:
            return jsonify({
                'success': False,
                'message': 'Collection name is required'
            }), 400
            
        name = data.get('name')
        description = data.get('description', '')
        
        # Check if collection with this name already exists
        existing = Collection.query.filter_by(name=name).first()
        if existing:
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
        
        return jsonify({
            'success': True,
            'message': f'Collection "{name}" created successfully',
            'collection_id': new_collection.id
        })
    except Exception as e:
        logger.exception("Error creating collection")
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
