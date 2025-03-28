import os
import time
import logging
import threading
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from models import Document, DocumentChunk
from utils.document_processor import process_pdf
from utils.vector_store import VectorStore
from utils.citation_manager import extract_citation_info
from utils.web_scraper import scrape_website, chunk_text

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize database connection
DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL)
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)

# Initialize vector store
vector_store = VectorStore()

class BackgroundProcessor:
    """
    Background processor for handling document processing.
    Runs in a separate thread to process documents that haven't been processed yet.
    """
    def __init__(self, batch_size=1, sleep_time=5):
        """
        Initialize the background processor.
        
        Args:
            batch_size (int): Number of documents to process in each batch
            sleep_time (int): Time to sleep between batches in seconds
        """
        self.batch_size = batch_size
        self.sleep_time = sleep_time
        self.running = False
        self.thread = None
        self.last_run_time = None
        self.documents_processed = 0
        
    def start(self):
        """Start the background processor if it's not already running."""
        if self.running:
            logger.info("Background processor already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._processing_loop)
        self.thread.daemon = True  # Thread will exit when main thread exits
        self.thread.start()
        logger.info("Background processor started")
        
    def stop(self):
        """Stop the background processor."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)  # Wait for thread to finish
            self.thread = None
        logger.info("Background processor stopped")
        
    def _processing_loop(self):
        """Main processing loop to find and process documents."""
        logger.info("Background processing loop started")
        
        while self.running:
            try:
                # Start a new session for this iteration
                session = Session()
                
                # Find unprocessed documents
                unprocessed_docs = session.query(Document).filter_by(
                    processed=False,
                ).limit(self.batch_size).all()
                
                if not unprocessed_docs:
                    logger.debug("No unprocessed documents found, sleeping...")
                    session.close()
                    time.sleep(self.sleep_time)
                    continue
                
                # Process each document
                for doc in unprocessed_docs:
                    try:
                        logger.info(f"Background processing document {doc.id}: {doc.filename} (type: {doc.file_type})")
                        
                        # Handle PDF documents
                        if doc.file_type == 'pdf':
                            if not doc.file_path or not os.path.exists(doc.file_path):
                                logger.warning(f"File not found for document {doc.id}: {doc.file_path}")
                                doc.processed = True  # Mark as processed to skip it
                                session.commit()
                                continue
                                
                            # Process the PDF
                            chunks, metadata = process_pdf(doc.file_path, doc.filename)
                        
                        # Handle website documents
                        elif doc.file_type == 'website':
                            if not doc.source_url:
                                logger.warning(f"URL not found for document {doc.id}")
                                doc.processed = True  # Mark as processed to skip it
                                session.commit()
                                continue
                                
                            # Process the website
                            logger.info(f"Processing website: {doc.source_url}")
                            result = scrape_website(doc.source_url, max_pages=10)
                            
                            chunks = []
                            for i, chunk_data in enumerate(result):
                                chunks.append({
                                    'text': chunk_data['text'],
                                    'metadata': {
                                        'url': chunk_data.get('metadata', {}).get('url', doc.source_url),
                                        'page_number': i  # Use index as a pseudo-page number
                                    }
                                })
                            
                            metadata = {
                                'title': doc.title or "Website Document",
                                'source_url': doc.source_url
                            }
                        
                        if not chunks or not metadata:
                            logger.warning(f"No content extracted from document {doc.id}")
                            doc.processed = True  # Mark as processed to skip it in future
                            session.commit()
                            continue
                        
                        # Update document metadata
                        doc.title = metadata.get('title', doc.title)
                        doc.page_count = metadata.get('page_count', doc.page_count)
                        doc.doi = metadata.get('doi')
                        doc.authors = metadata.get('authors')
                        doc.journal = metadata.get('journal')
                        doc.publication_year = metadata.get('publication_year')
                        doc.volume = metadata.get('volume')
                        doc.issue = metadata.get('issue')
                        doc.pages = metadata.get('pages')
                        doc.formatted_citation = metadata.get('formatted_citation')
                        doc.processed = True
                        doc.updated_at = datetime.utcnow()
                        
                        # Add chunks to database and vector store
                        for i, chunk in enumerate(chunks):
                            # Create metadata for the chunk
                            chunk_metadata = {
                                'document_id': doc.id,
                                'chunk_index': i,
                                'page_number': chunk.get('metadata', {}).get('page_number', None),
                                'document_title': doc.title or doc.filename,
                                'file_type': doc.file_type
                            }
                            
                            # Add to vector store
                            vector_store.add_text(chunk['text'], chunk_metadata)
                            
                            # Create database record
                            chunk_record = DocumentChunk(
                                document_id=doc.id,
                                chunk_index=i,
                                page_number=chunk.get('metadata', {}).get('page_number', None),
                                text_content=chunk['text']
                            )
                            
                            session.add(chunk_record)
                        
                        # Save changes
                        session.commit()
                        self.documents_processed += 1
                        self.last_run_time = datetime.utcnow()
                        logger.info(f"Successfully processed document {doc.id} with {len(chunks)} chunks")
                        
                    except Exception as e:
                        logger.exception(f"Error processing document {doc.id}: {str(e)}")
                        session.rollback()
                        # Mark as processed but with error flag (could add an error field to Document model)
                        try:
                            # Re-query the document to get a fresh instance
                            doc = session.query(Document).get(doc.id)
                            if doc:
                                doc.processed = True  # Mark as processed to avoid infinite retries
                                session.commit()
                        except Exception as commit_error:
                            logger.exception(f"Error updating document status: {str(commit_error)}")
                            session.rollback()
                
                # After processing batch, sleep before next iteration
                time.sleep(self.sleep_time)
                
            except Exception as e:
                logger.exception(f"Error in background processing loop: {str(e)}")
                time.sleep(self.sleep_time)  # Sleep to avoid tight error loop
                
            finally:
                # Always close the session
                session.close()
        
        logger.info("Background processing loop ended")
        
    def get_status(self):
        """Get the current status of the background processor."""
        return {
            'running': self.running,
            'last_run': self.last_run_time.isoformat() if self.last_run_time else None,
            'documents_processed': self.documents_processed
        }


# Singleton instance
background_processor = BackgroundProcessor(batch_size=1, sleep_time=10)