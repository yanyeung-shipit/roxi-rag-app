"""
Simple script to process a batch of chunks and add them to the vector store.
This script is designed to be run frequently via cron job or similar.
"""
import logging
import sys
from add_single_chunk import process_multiple_chunks
from check_progress import check_progress

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('rebuild_batch.log')
    ]
)
logger = logging.getLogger(__name__)

# Number of chunks to process in this batch
BATCH_SIZE = 3

def main():
    """Process a batch of chunks and report progress."""
    try:
        # Get the current progress
        initial_progress = check_progress()
        initial_count = initial_progress.get('vector_count', 0)
        total_chunks = initial_progress.get('db_count', 0)
        logger.info(f"Starting with {initial_count}/{total_chunks} chunks processed ({initial_progress.get('progress_pct', 0):.1f}%)")
        
        # Process multiple chunks
        logger.info(f"Processing up to {BATCH_SIZE} chunks...")
        result = process_multiple_chunks(BATCH_SIZE)
        
        # Log the results
        logger.info(f"Processed {result['chunks_processed']} chunks ({result['chunks_succeeded']} succeeded)")
        if result['processing_complete']:
            logger.info("All chunks have been processed")
        
        # Get the updated progress
        final_progress = check_progress()
        final_count = final_progress.get('vector_count', 0)
        chunks_added = final_count - initial_count
        logger.info(f"Added {chunks_added} chunks to vector store")
        logger.info(f"Current progress: {final_progress.get('progress_pct', 0):.1f}% complete")
        
        return 0  # Success
    
    except Exception as e:
        logger.error(f"Error processing batch: {e}", exc_info=True)
        return 1  # Error

if __name__ == "__main__":
    sys.exit(main())