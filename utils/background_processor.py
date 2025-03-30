import os
import time
import random
import logging
import threading
import urllib.parse
import gc
import psutil
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from models import Document, DocumentChunk
from utils.document_processor import process_pdf
from utils.vector_store import VectorStore
from utils.citation_manager import extract_citation_info
from utils.web_scraper import scrape_website, chunk_text
from utils.resource_monitor import get_resource_data, determine_processing_mode, get_system_resources, set_processing_status

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

# Global background processor instance
_background_processor = None

# Pre-configured singleton instance, will be set at the end of the file
background_processor = None

def reduce_memory_usage():
    """
    Aggressively reduce memory usage by clearing caches and forcing garbage collection.
    This is primarily used during deep sleep to minimize memory footprint.
    
    Returns:
        dict: Memory statistics before and after reduction
    """
    import gc
    import psutil
    import sys
    
    # Get before stats
    process = psutil.Process()
    before_mem = process.memory_info().rss / 1024 / 1024  # MB
    
    # Clear embedding cache if available
    try:
        from utils.llm_service import clear_embedding_cache
        cache_entries = clear_embedding_cache()
        logger.info(f"Cleared {cache_entries} entries from embedding cache")
    except Exception as e:
        logger.warning(f"Failed to clear embedding cache: {str(e)}")
    
    # Clear any module-specific caches that might be holding memory
    if 'openai' in sys.modules:
        # Clear OpenAI API response caches if the module is loaded
        try:
            # Reset thread pool if it exists
            if hasattr(sys.modules['openai'], '_Thread__initialized'):
                sys.modules['openai']._Thread__initialized = False
        except Exception as e:
            logger.warning(f"Failed to reset OpenAI thread pool: {str(e)}")
    
    # Clear SQLAlchemy caches if present
    if 'sqlalchemy' in sys.modules:
        try:
            from sqlalchemy import event
            from sqlalchemy.engine import Engine
            engine = _background_processor.engine if _background_processor else None
            if engine:
                # Dispose connections
                engine.dispose()
                logger.info("SQLAlchemy connection pool disposed")
        except Exception as e:
            logger.warning(f"Failed to dispose SQLAlchemy connections: {str(e)}")
    
    # Clear Python's internal caches
    gc.collect(generation=2)  # Full collection
    
    # Get after stats
    after_mem = process.memory_info().rss / 1024 / 1024  # MB
    
    saved = before_mem - after_mem
    logger.info(f"Memory reduction: Before={before_mem:.1f}MB, After={after_mem:.1f}MB, Saved={saved:.1f}MB")
    
    return {
        "before_mb": round(before_mem, 1),
        "after_mb": round(after_mem, 1),
        "saved_mb": round(saved, 1)
    }

def force_deep_sleep():
    """
    Force the background processor into deep sleep mode.
    This function immediately puts the background processor into deep sleep
    mode, which significantly reduces CPU and memory usage.
    
    Returns:
        bool: True if deep sleep mode was activated, False otherwise
    """
    global _background_processor
    
    if _background_processor is None:
        logger.warning("Background processor not initialized, cannot force deep sleep")
        return False
        
    try:
        logger.info("Manually forcing deep sleep mode via API request")
        
        # Set to extreme values to ensure persistent deep sleep
        _background_processor.consecutive_idle_cycles = _background_processor.deep_sleep_threshold * 2
        _background_processor.in_deep_sleep = True
        
        # Set a much longer sleep time for manual activation - 30 minutes
        _background_processor.sleep_time = _background_processor.deep_sleep_time * 3  # 30 minutes
        
        # Set a flag to indicate manual activation, which will prevent auto-exit
        _background_processor.manually_activated_sleep = True
        
        # Aggressively release memory and clear caches
        memory_stats = reduce_memory_usage()
        
        # Now that we're in deep sleep, set a more aggressive cache cleaning approach
        try:
            from utils.llm_service import _CACHE_TTL, _CACHE_CLEANUP_INTERVAL
            import sys
            # If available, override with more aggressive settings during deep sleep
            sys.modules['utils.llm_service']._CACHE_TTL = 60 * 1  # 1 minute TTL
            sys.modules['utils.llm_service']._CACHE_CLEANUP_INTERVAL = 30  # Clean up every 30 seconds
            logger.info(f"Set aggressive cache timeout during deep sleep: TTL={60 * 1}s, Cleanup={30}s")
        except Exception as e:
            logger.warning(f"Failed to update cache settings: {str(e)}")
        
        # Log detailed info about the sleep activation
        logger.info(f"Deep sleep mode activated manually. Sleep time set to {_background_processor.sleep_time}s")
        logger.info(f"Memory usage reduced by {memory_stats['saved_mb']}MB to {memory_stats['after_mb']}MB")
        
        # Pass 0.0 as rate when manually activating deep sleep
        set_processing_status("deep_sleep", 0.0)
        return True
    except Exception as e:
        logger.error(f"Error forcing deep sleep mode: {str(e)}")
        return False

def exit_deep_sleep():
    """
    Exit deep sleep mode and reset to normal processing.
    This function is called when a new document is uploaded, to ensure it gets processed.
    
    Returns:
        bool: True if deep sleep mode was exited, False otherwise
    """
    global _background_processor
    
    if _background_processor is None:
        logger.warning("Background processor not initialized, cannot exit deep sleep")
        return False
        
    try:
        was_in_deep_sleep = False
        
        # Check if deep sleep was activated manually and create a clearer log message
        if _background_processor.manually_activated_sleep:
            logger.info("Exiting manually-activated deep sleep mode due to explicit user action")
            was_in_deep_sleep = True
        elif _background_processor.in_deep_sleep:
            logger.info("Exiting automatic deep sleep mode due to new document upload")
            was_in_deep_sleep = True
        else:
            # Already not in deep sleep
            return False
            
        # Reset all sleep-related flags regardless of how it was activated
        _background_processor.in_deep_sleep = False
        _background_processor.manually_activated_sleep = False
        _background_processor.consecutive_idle_cycles = 0
        _background_processor.sleep_time = _background_processor.base_sleep_time
        
        # Still run memory reduction for cleanup, but we expect it to be less effective
        # since we're about to start processing again
        memory_stats = reduce_memory_usage()
        
        # Reset cache settings to normal values when exiting deep sleep
        try:
            import sys
            # Reset to default values for normal operation
            sys.modules['utils.llm_service']._CACHE_TTL = 60 * 3  # 3 minutes TTL
            sys.modules['utils.llm_service']._CACHE_CLEANUP_INTERVAL = 60 * 1  # Clean up every minute
            logger.info(f"Reset cache settings to normal: TTL={60 * 3}s, Cleanup={60 * 1}s")
        except Exception as e:
            logger.warning(f"Failed to reset cache settings: {str(e)}")
        
        logger.info(f"Deep sleep mode exited. Sleep time reset to {_background_processor.sleep_time}s")
        logger.info(f"Memory status after exit: {memory_stats['after_mb']}MB (released {memory_stats['saved_mb']}MB)")
        
        set_processing_status("active", 0.0)  # Reset status to active
        return True
    except Exception as e:
        logger.error(f"Error exiting deep sleep mode: {str(e)}")
        return False
        
def is_in_deep_sleep():
    """
    Check if the background processor is currently in deep sleep mode.
    
    Returns:
        bool: True if the background processor is in deep sleep mode, False otherwise
    """
    global _background_processor
    
    if _background_processor is None:
        logger.warning("Background processor not initialized, cannot check deep sleep status")
        return False
        
    return _background_processor.in_deep_sleep

def initialize_background_processor(batch_size=1, sleep_time=5):
    """
    Initialize and start the background processor.
    This function is called from main.py to start the background processor.
    
    Args:
        batch_size (int): Number of documents to process in each batch
        sleep_time (int): Time to sleep between batches in seconds
    
    Returns:
        BackgroundProcessor: The background processor instance
    """
    global _background_processor
    
    # If already initialized, just return the existing instance
    if _background_processor is not None:
        logger.info("Background processor already initialized")
        return _background_processor
    
    # Create a new background processor
    _background_processor = BackgroundProcessor(batch_size=batch_size, sleep_time=sleep_time)
    
    # Start the background processor
    _background_processor.start()
    
    return _background_processor

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
        self.base_sleep_time = sleep_time
        self.sleep_time = sleep_time  # Current sleep time (will adapt)
        self.max_sleep_time = 300     # Maximum sleep time (5 minutes)
        self.deep_sleep_time = 600    # Deep sleep mode (10 minutes)
        self.consecutive_idle_cycles = 0  # Track consecutive idle cycles
        self.deep_sleep_threshold = 10  # Cycles before entering deep sleep
        self.in_deep_sleep = False    # Deep sleep mode flag
        self.manually_activated_sleep = False  # Flag for when sleep mode was manually activated
        self.running = False
        self.thread = None
        self.last_run_time = None
        self.documents_processed = 0
        self.last_work_found_time = time.time()  # Track when we last found work
        
        # Create SQLAlchemy engine and session
        self.engine = create_engine(DATABASE_URL)
        self.Session = scoped_session(sessionmaker(bind=self.engine))
        
        # Init vector store
        self.vector_store = VectorStore()
        
    def _create_session(self):
        """Create a new database session. Used to recover from transaction errors."""
        try:
            return self.Session()
        except Exception as e:
            logger.exception(f"Error creating session: {str(e)}")
            # If we can't create a session through the scoped session, try direct creation
            return sessionmaker(bind=self.engine)()
        
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
                session = self._create_session()
                
                # First, check if there are any processed website documents that have more content available
                # These are documents where file_size > 0 and file_size > number of chunks
                try:
                    # Find documents with more content to load
                    from sqlalchemy import func
                    subquery = session.query(
                        DocumentChunk.document_id,
                        func.count(DocumentChunk.id).label('chunk_count')
                    ).group_by(DocumentChunk.document_id).subquery()
                    
                    # Query for documents that:
                    # 1. Are website documents (since only websites support "load more")
                    # 2. Are already processed (so their initial content is available)
                    # 3. Have file_size > 0 (meaning they have more content available)
                    # 4. Have fewer chunks than file_size (the remaining content)
                    documents_with_more_content = session.query(Document).join(
                        subquery, 
                        Document.id == subquery.c.document_id
                    ).filter(
                        Document.file_type == 'website',
                        Document.processed == True,
                        Document.file_size > 0,
                        Document.file_size > subquery.c.chunk_count
                    ).limit(self.batch_size).all()
                    
                    if documents_with_more_content:
                        import urllib.parse
                        from utils.web_scraper import create_minimal_content_for_topic
                        
                        for doc in documents_with_more_content:
                            try:
                                logger.info(f"Loading more content for document {doc.id}: {doc.title}")
                                
                                # Get the current number of chunks
                                current_chunk_count = len(doc.chunks)
                                total_possible_chunks = doc.file_size or 0
                                
                                # Determine how many more chunks to load (maximum 100 at a time)
                                chunks_to_load = min(100, total_possible_chunks - current_chunk_count)
                                logger.info(f"Attempting to load {chunks_to_load} more chunks for document {doc.id}")
                                
                                # Get the document URL
                                url = doc.source_url
                                if not url:
                                    logger.warning(f"Document {doc.id} has no source URL, skipping")
                                    continue
                                
                                # Get fresh content to ensure we have all chunks
                                chunks = create_minimal_content_for_topic(url)
                                
                                if not chunks:
                                    logger.warning(f"Failed to retrieve additional content for document {doc.id}")
                                    continue
                                
                                # Skip chunks we already have and take only the next batch
                                start_index = current_chunk_count
                                end_index = min(start_index + chunks_to_load, len(chunks))
                                
                                if start_index >= len(chunks):
                                    logger.info(f"No additional content available for document {doc.id}")
                                    continue
                                
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
                                        
                                        session.add(chunk_record)
                                        
                                        added_count += 1
                                    except Exception as e:
                                        logger.error(f"Error adding chunk {i+start_index}: {str(e)}")
                                
                                # Commit changes after processing all chunks for this document
                                session.commit()
                                vector_store._save()
                                
                                logger.info(f"Added {added_count} more chunks to document {doc.id}")
                                
                                # Update document if we've loaded all chunks
                                new_total = current_chunk_count + added_count
                                if new_total >= total_possible_chunks:
                                    logger.info(f"Document {doc.id} now has all {new_total} chunks loaded")
                                else:
                                    logger.info(f"Document {doc.id} now has {new_total}/{total_possible_chunks} chunks loaded")
                                
                                # Force Python garbage collection to free memory
                                import gc
                                gc.collect()
                                
                            except Exception as e:
                                logger.exception(f"Error loading additional content for document {doc.id}: {str(e)}")
                                session.rollback()
                                
                    # We processed some documents with more content, sleep before checking for unprocessed documents
                    if documents_with_more_content:
                        # Reset idle counter since we found work
                        self.consecutive_idle_cycles = 0
                        self.sleep_time = self.base_sleep_time  # Reset sleep time to base value
                        
                        logger.info(f"Processed {len(documents_with_more_content)} documents with more content, reset sleep time to {self.sleep_time}s")
                        time.sleep(self.sleep_time / 2)  # Sleep half the normal time before looking for unprocessed docs
                
                except Exception as e:
                    logger.exception(f"Error checking for documents with more content: {str(e)}")
                
                # Check for unprocessed documents
                try:
                    # First, look for documents with processing_state set (partially processed)
                    partially_processed_docs = []
                    try:
                        logger.debug("Checking for partially processed documents...")
                        partially_processed_docs = session.query(Document).filter(
                            Document.processed == False,
                            Document.processing_state.isnot(None)
                        ).limit(self.batch_size).all()
                        
                        if partially_processed_docs:
                            logger.info(f"Found {len(partially_processed_docs)} partially processed documents")
                    except Exception as e:
                        logger.warning(f"Error finding partially processed documents: {str(e)}")
                        # Close session and create a new one to recover from transaction errors
                        session.close()
                        session = self._create_session()
                    
                    # If no partially processed docs, look for any unprocessed docs
                    if not partially_processed_docs:
                        unprocessed_docs = session.query(Document).filter_by(
                            processed=False,
                        ).limit(self.batch_size).all()
                    else:
                        unprocessed_docs = partially_processed_docs
                    
                    if not unprocessed_docs:
                        # No work found, implement adaptive sleep time
                        self.consecutive_idle_cycles += 1
                        
                        # Periodically reduce memory even before deep sleep
                        if self.consecutive_idle_cycles > 5 and self.consecutive_idle_cycles % 5 == 0:
                            logger.info(f"Reducing memory after {self.consecutive_idle_cycles} idle cycles")
                            memory_stats = reduce_memory_usage()
                            logger.info(f"Memory usage reduced by {memory_stats['saved_mb']}MB to {memory_stats['after_mb']}MB")
                        
                        # Check if we should enter deep sleep mode
                        if self.consecutive_idle_cycles >= self.deep_sleep_threshold and not self.in_deep_sleep:
                            self.in_deep_sleep = True
                            self.sleep_time = self.deep_sleep_time
                            
                            # Reduce memory consumption when entering automatic deep sleep
                            memory_stats = reduce_memory_usage()
                            
                            logger.info(f"Entering deep sleep mode after {self.consecutive_idle_cycles} idle cycles, sleep time set to {self.deep_sleep_time}s")
                            logger.info(f"Memory usage reduced by {memory_stats['saved_mb']}MB to {memory_stats['after_mb']}MB")
                        # Otherwise use exponential backoff
                        elif not self.in_deep_sleep and self.consecutive_idle_cycles > 3:
                            # Double sleep time after 3 idle cycles (up to max limit)
                            self.sleep_time = min(self.sleep_time * 2, self.max_sleep_time)
                            logger.debug(f"No unprocessed documents found for {self.consecutive_idle_cycles} cycles, increasing sleep to {self.sleep_time}s")
                        elif self.in_deep_sleep:
                            logger.debug(f"In deep sleep mode, sleeping for {self.sleep_time}s")
                        else:
                            logger.debug(f"No unprocessed documents found, sleeping for {self.sleep_time}s...")
                            
                        session.close()
                        time.sleep(self.sleep_time)
                        continue
                        
                except Exception as e:
                    # Handle database transaction errors
                    logger.exception(f"Database error checking for unprocessed documents: {str(e)}")
                    # Close session and create a new one
                    try:
                        session.close()
                    except:
                        pass
                    time.sleep(2)  # Brief pause to let database recover
                    session = self._create_session()
                    continue
                
                # If manually activated sleep, we don't want to process work at all
                if self.manually_activated_sleep:
                    logger.info(f"Staying in deep sleep mode despite work (manually activated)")
                    
                    # Maintain high sleep time
                    self.sleep_time = max(self.sleep_time, self.deep_sleep_time * 3)
                    self.in_deep_sleep = True
                    
                    # Always reduce memory in manual sleep mode - reliable cleanup
                    # This is a guaranteed memory reduction even during manual sleep
                    memory_stats = reduce_memory_usage()
                    logger.info(f"Periodic memory cleanup during manual sleep: {memory_stats['saved_mb']}MB freed")
                    
                    # Skip processing - go straight to sleep
                    session.close()
                    time.sleep(self.sleep_time)
                    continue
                
                # If we got here, we have work to do, reset the idle counter and sleep time
                self.consecutive_idle_cycles = 0
                self.sleep_time = self.base_sleep_time  # Reset sleep time to base value
                
                # If we were in deep sleep, exit that mode (only happens for automatic deep sleep)
                if self.in_deep_sleep:
                    self.in_deep_sleep = False
                    logger.info(f"Exiting deep sleep mode, work found!")
                
                logger.debug(f"Found work to do, resetting sleep time to {self.sleep_time}s")
                
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
                            
                            # IMPORTANT: We're abandoning the multi-page approach completely
                            # Instead, we'll use a direct extraction approach for all websites that's optimized for maximum content
                            
                            # Always use the direct method now, bypassing the crawler
                            # This should produce more content chunks by focusing extraction efforts on a single page
                            from utils.web_scraper import extract_website_direct
                            logger.info(f"Using direct intensive extraction for website: {doc.source_url}")
                            
                            # Try the new direct extraction method
                            result = extract_website_direct(doc.source_url)
                            
                            # If the direct method fails or produces too little content, try the topic extraction as backup
                            if not result or len(result) < 5:
                                logger.info(f"Direct extraction produced insufficient content ({len(result) if result else 0} chunks), trying specialized extraction")
                                from utils.web_scraper import create_minimal_content_for_topic
                                result = create_minimal_content_for_topic(doc.source_url)
                                
                            # Log the result size
                            logger.info(f"Extracted {len(result) if result else 0} chunks from website")
                            
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
                                'file_type': doc.file_type,
                                'doi': doc.doi,
                                'formatted_citation': doc.formatted_citation,
                                'source_url': doc.source_url,
                                'citation': chunk.get('metadata', {}).get('citation', doc.formatted_citation)
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
        """Get the current status of the background processor with resource information."""
        # Get current resource information
        resource_data = get_resource_data()
        
        # Get system resources for real-time data
        system_resources = get_system_resources()
        
        # Determine optimal processing mode based on resources
        proc_mode, batch_size, resource_limited = determine_processing_mode(system_resources)
        
        # Count how many documents have more content to load
        try:
            session = self._create_session()
            from sqlalchemy import func
            
            # Create subquery to get the chunk count for each document
            subquery = session.query(
                DocumentChunk.document_id,
                func.count(DocumentChunk.id).label('chunk_count')
            ).group_by(DocumentChunk.document_id).subquery()
            
            # Count documents waiting for more content loading
            waiting_documents = session.query(Document).join(
                subquery, 
                Document.id == subquery.c.document_id
            ).filter(
                Document.file_type == 'website',
                Document.processed == True,
                Document.file_size > 0,
                Document.file_size > subquery.c.chunk_count
            ).count()
            
            # Count documents waiting for initial processing
            unprocessed_documents = session.query(Document).filter_by(
                processed=False
            ).count()
            
            # Count total documents and chunks in database
            total_documents = session.query(Document).count()
            total_chunks = session.query(DocumentChunk).count()
            
            # Count processed chunks in vector store
            processed_chunks = len(self.vector_store.get_processed_chunk_ids())
            
            # Calculate processing metrics
            processing_complete_percent = (processed_chunks / total_chunks * 100) if total_chunks > 0 else 0
            
            # Calculate estimated remaining time
            estimated_seconds_remaining = 0
            processing_rate = resource_data.get('processing_rate', 0)
            
            if processing_rate > 0:
                remaining_chunks = total_chunks - processed_chunks
                estimated_seconds_remaining = remaining_chunks / processing_rate
            
            # Format time for display
            if estimated_seconds_remaining > 0:
                minutes, seconds = divmod(int(estimated_seconds_remaining), 60)
                hours, minutes = divmod(minutes, 60)
                days, hours = divmod(hours, 24)
                
                if days > 0:
                    formatted_time = f"{days}d {hours}h {minutes}m"
                elif hours > 0:
                    formatted_time = f"{hours}h {minutes}m"
                else:
                    formatted_time = f"{minutes}m {seconds}s"
            else:
                formatted_time = "Unknown"
            
            session.close()
        except Exception as e:
            logger.exception(f"Error getting document counts: {str(e)}")
            waiting_documents = 0
            unprocessed_documents = 0
            total_documents = 0
            total_chunks = 0
            processed_chunks = 0
            processing_complete_percent = 0
            formatted_time = "Unknown"
        
        # Set current processing status in resource monitor
        current_mode = "idle"
        if self.running and unprocessed_documents > 0:
            current_mode = proc_mode
        
        # Respect deep sleep mode when set manually
        if self.in_deep_sleep:
            current_mode = "deep_sleep"
            
        set_processing_status(current_mode, resource_data.get('processing_rate', 0))
        
        # Create status object with comprehensive information
        return {
            # Basic status
            'running': self.running,
            'last_run': self.last_run_time.isoformat() if self.last_run_time else None,
            'documents_processed': self.documents_processed,
            'unprocessed_documents': unprocessed_documents,
            'documents_waiting_for_more_content': waiting_documents,
            'current_sleep_time': self.sleep_time,
            'consecutive_idle_cycles': self.consecutive_idle_cycles,
            'in_deep_sleep': self.in_deep_sleep,
            'deep_sleep_threshold': self.deep_sleep_threshold,
            
            # Resource information
            'system_resources': {
                'cpu_percent': system_resources['cpu_percent'],
                'memory_percent': system_resources['memory_percent'],
                'memory_available_mb': system_resources['memory_available_mb'],
                'resource_limited': resource_limited
            },
            
            # Processing mode information
            'processing_mode': {
                'current_mode': current_mode,
                'recommended_mode': proc_mode,
                'recommended_batch_size': batch_size,
                'resource_constrained': resource_limited
            },
            
            # Processing progress metrics
            'processing_metrics': {
                'total_documents': total_documents,
                'total_chunks': total_chunks,
                'processed_chunks': processed_chunks,
                'percent_complete': round(processing_complete_percent, 1),
                'estimated_time_remaining': formatted_time,
                'processing_rate_chunks_per_second': round(resource_data.get('processing_rate', 0), 2)
            }
        }


# Use a single shared instance for the background processor
# This synchronizes _background_processor (for sleep control) with background_processor (for API usage)
_background_processor = BackgroundProcessor(batch_size=1, sleep_time=10)
background_processor = _background_processor

# Initialize both with the same instance to ensure sleep mode functions correctly
# and deep sleep state is properly reported through the API