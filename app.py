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
            flash('No file part')
            return redirect(request.url)
        
        file = request.files['pdf_file']
        
        # Check if file was selected
        if file.filename == '':
            flash('No file selected')
            return redirect(request.url)
        
        # Process valid file
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(TEMP_FOLDER, filename)
            file.save(filepath)
            
            # Process PDF and add to vector store
            chunks = process_pdf(filepath, filename)
            for chunk in chunks:
                vector_store.add_text(chunk['text'], chunk['metadata'])
            
            # Remove temporary file
            os.remove(filepath)
            
            return jsonify({
                'success': True, 
                'message': f'Successfully processed {filename}',
                'chunks': len(chunks)
            })
        else:
            return jsonify({
                'success': False, 
                'message': 'Invalid file type. Only PDF files are allowed.'
            }), 400
    except Exception as e:
        logger.exception("Error processing PDF")
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
            return jsonify({
                'success': False, 
                'message': 'URL is required'
            }), 400
        
        # Scrape website and add to vector store
        chunks = scrape_website(url)
        for chunk in chunks:
            vector_store.add_text(chunk['text'], chunk['metadata'])
        
        return jsonify({
            'success': True, 
            'message': f'Successfully processed website: {url}',
            'chunks': len(chunks)
        })
    except Exception as e:
        logger.exception("Error processing website")
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
