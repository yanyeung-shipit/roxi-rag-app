#!/usr/bin/env python3
"""
Test the batch rebuild processor with a small batch size and limited run.
This script processes just a few chunks to verify the batch processor works correctly.
"""

import os
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the current directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from batch_rebuild_to_target import BatchProcessor

def test_batch_processor():
    """Run a small test of the batch processor."""
    logger.info("Starting batch processor test")
    
    # Create processor with small batch size and run for just 2 batches
    processor = BatchProcessor(batch_size=2, target_percentage=100.0)
    
    # Get initial progress
    progress = processor.get_progress()
    logger.info(f"Initial progress: {progress['percentage']}% "
               f"({progress['processed_chunks']}/{progress['total_chunks']} chunks)")
    logger.info(f"Estimated time remaining: {progress['estimated_time_remaining']}")
    
    # Process just 2 batches for testing
    batches_to_process = 2
    batches_processed = 0
    chunks_processed = 0
    
    while batches_processed < batches_to_process:
        # Get next batch
        chunks = processor.get_next_chunk_batch()
        
        if not chunks:
            logger.info("No more chunks to process")
            break
        
        # Process the batch
        logger.info(f"Processing test batch {batches_processed + 1} of {batches_to_process}")
        results = processor.process_batch(chunks)
        
        # Update counters
        batches_processed += 1
        chunks_processed += results["successful"]
        
        # Log results
        logger.info(f"Batch {batches_processed} results: {results['successful']}/{results['total']} successful")
        
        # Update progress
        progress = processor.get_progress()
        logger.info(f"Progress: {progress['percentage']}% "
                  f"({progress['processed_chunks']}/{progress['total_chunks']} chunks)")
        logger.info(f"Updated time remaining: {progress['estimated_time_remaining']}")
    
    # Final progress
    progress = processor.get_progress()
    logger.info(f"Test completed. Processed {chunks_processed} chunks in {batches_processed} batches")
    logger.info(f"Final progress: {progress['percentage']}% "
               f"({progress['processed_chunks']}/{progress['total_chunks']} chunks)")
    logger.info(f"Final estimated time remaining: {progress['estimated_time_remaining']}")
    
    return chunks_processed > 0

if __name__ == "__main__":
    success = test_batch_processor()
    sys.exit(0 if success else 1)