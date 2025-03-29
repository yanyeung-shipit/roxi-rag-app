"""
Script to continuously process chunks from the database into the vector store.
This script will run until all chunks are processed or it is stopped.
"""
import sys
import time
import logging
from app import app, Document, DocumentChunk
from utils.vector_store import VectorStore
from add_single_chunk import add_next_chunk
from check_progress import check_progress

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def continuous_rebuild(max_chunks=None, delay_seconds=2):
    """
    Continuously process chunks until all are processed or the maximum is reached.
    
    Args:
        max_chunks (int, optional): Maximum number of chunks to process. If None, process all.
        delay_seconds (int, optional): Delay between chunks to avoid API rate limits.
    """
    try:
        chunk_count = 0
        last_progress_check = time.time()
        progress_check_interval = 30  # seconds
        
        logger.info("Starting continuous vector store rebuild...")
        
        while True:
            # Check progress periodically
            if time.time() - last_progress_check > progress_check_interval:
                progress = check_progress()
                last_progress_check = time.time()
                
                # If 100% complete, exit
                if progress and progress['progress_percent'] >= 99.9:
                    logger.info("Vector store rebuild is complete!")
                    return True
            
            # Process the next chunk
            result = add_next_chunk()
            
            # If no more chunks to process or reached max chunks, exit
            if not result:
                logger.info("No more chunks to process or encountered an error.")
                progress = check_progress()
                return progress['progress_percent'] >= 99.9
            
            # Increment chunk count
            chunk_count += 1
            
            # Check if we've reached the maximum number of chunks to process
            if max_chunks and chunk_count >= max_chunks:
                logger.info(f"Processed {chunk_count} chunks (max: {max_chunks})")
                progress = check_progress()
                return progress['progress_percent'] >= 99.9
                
            # Small delay to avoid API rate limits
            time.sleep(delay_seconds)
            
    except KeyboardInterrupt:
        logger.info("Rebuild process interrupted by user.")
        return False
    except Exception as e:
        logger.error(f"Error in continuous rebuild: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Get the maximum number of chunks to process from command line args
    max_chunks = None
    if len(sys.argv) > 1:
        try:
            max_chunks = int(sys.argv[1])
        except ValueError:
            logger.error(f"Invalid max_chunks: {sys.argv[1]}. Using unlimited.")
    
    # Run the continuous rebuild
    continuous_rebuild(max_chunks=max_chunks)