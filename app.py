import os
import logging
import tempfile
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
from werkzeug.utils import secure_filename
from utils.document_processor import process_pdf
from utils.web_scraper import scrape_website
from utils.vector_store import VectorStore
from utils.llm_service import generate_response

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")

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

@app.route('/upload_pdf', methods=['POST'])
def upload_pdf():
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
            
            # Check file size before saving
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)  # Reset file pointer
            
            if file_size > 50 * 1024 * 1024:  # 50MB limit
                logger.warning(f"PDF file too large: {file_size / (1024*1024):.2f} MB")
                return jsonify({
                    'success': False, 
                    'message': f'PDF file too large ({file_size / (1024*1024):.2f} MB). Maximum size is 50 MB.'
                }), 400
            
            # Save file to temporary location
            filepath = os.path.join(TEMP_FOLDER, filename)
            file.save(filepath)
            logger.debug(f"Saved file temporarily to {filepath}")
            
            try:
                # Process PDF and add to vector store
                chunks = process_pdf(filepath, filename)
                logger.info(f"Successfully processed PDF with {len(chunks)} chunks")
                
                # Save chunks in batches to prevent timeouts
                batch_size = 50
                total_batches = (len(chunks) + batch_size - 1) // batch_size
                
                try:
                    for i in range(0, len(chunks), batch_size):
                        batch = chunks[i:i + batch_size]
                        logger.debug(f"Processing batch {(i // batch_size) + 1}/{total_batches} with {len(batch)} chunks")
                        
                        for chunk in batch:
                            vector_store.add_text(chunk['text'], chunk['metadata'])
                    
                    # Explicitly force a save after all batches are processed
                    logger.debug("Forcing vector store save after batch processing")
                    vector_store._save()
                except Exception as batch_error:
                    logger.exception(f"Error processing batch: {str(batch_error)}")
                    raise batch_error
                finally:
                    # Remove temporary file in all cases
                    if os.path.exists(filepath):
                        os.remove(filepath)
                        logger.debug("Temporary file removed")
                
                return jsonify({
                    'success': True, 
                    'message': f'Successfully processed {filename}',
                    'chunks': len(chunks)
                })
            except Exception as processing_error:
                # Make sure we clean up the temporary file if there was an error
                if os.path.exists(filepath):
                    os.remove(filepath)
                    logger.debug("Temporary file removed after error")
                
                # Re-raise the exception to be caught by the outer try-except
                raise processing_error
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
        
        # Scrape website and add to vector store
        chunks = scrape_website(url)
        
        if not chunks:
            logger.warning(f"No content extracted from website: {url}")
            return jsonify({
                'success': False, 
                'message': 'Could not extract any content from the provided URL'
            }), 400
            
        logger.info(f"Successfully scraped website with {len(chunks)} chunks")
        
        # Process chunks in batches to prevent timeouts
        batch_size = 50
        total_batches = (len(chunks) + batch_size - 1) // batch_size
        
        try:
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i + batch_size]
                logger.debug(f"Processing batch {(i // batch_size) + 1}/{total_batches} with {len(batch)} chunks")
                
                for chunk in batch:
                    vector_store.add_text(chunk['text'], chunk['metadata'])
            
            # Explicitly force a save after all batches are processed
            logger.debug("Forcing vector store save after batch processing")
            vector_store._save()
            
            return jsonify({
                'success': True, 
                'message': f'Successfully processed website: {url}',
                'chunks': len(chunks)
            })
        except Exception as batch_error:
            logger.exception(f"Error processing website batch: {str(batch_error)}")
            raise batch_error
            
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
        stats = vector_store.get_stats()
        return jsonify({
            'success': True,
            'stats': stats
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
        return jsonify({
            'success': True,
            'message': 'Vector store cleared successfully'
        })
    except Exception as e:
        logger.exception("Error clearing vector store")
        return jsonify({
            'success': False, 
            'message': f'Error clearing vector store: {str(e)}'
        }), 500
