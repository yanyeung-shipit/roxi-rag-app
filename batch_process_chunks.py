#!/usr/bin/env python3
"""
Batch process multiple chunks efficiently.
This script processes multiple chunks in a single Python process to minimize overhead.
"""

import sys
import time
import logging
import argparse
from typing import List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)
logger = logging.getLogger(__name__)

# Import application modules
from app import app
from models import db, DocumentChunk
from utils.vector_store import VectorStore
from direct_process_chunk import SimpleEmbeddingService, process_chunk

def get_unprocessed_chunk_ids(limit: int = 10) -> List[int]:
    """
    Get a list of unprocessed chunk IDs.
    
    Args:
        limit (int): Maximum number of chunks to retrieve
        
    Returns:
        List[int]: List of unprocessed chunk IDs
    """
    # Import here to avoid circular imports
    from find_unprocessed_chunks import find_unprocessed_chunks
    
    return find_unprocessed_chunks(limit)

def batch_process_chunks(num_chunks: int = 5) -> None:
    """
    Process multiple chunks efficiently within a single process.
    
    Args:
        num_chunks (int): Number of chunks to process
    """
    start_time = time.time()
    logger.info(f"Starting batch processing of up to {num_chunks} chunks")
    
    # Get chunk IDs to process
    chunk_ids = get_unprocessed_chunk_ids(num_chunks)
    if not chunk_ids:
        logger.info("No unprocessed chunks found. All chunks are processed!")
        return
    
    logger.info(f"Found {len(chunk_ids)} unprocessed chunks to process")
    
    # Process each chunk
    successful = 0
    failed = 0
    
    for i, chunk_id in enumerate(chunk_ids):
        chunk_start = time.time()
        logger.info(f"Processing chunk {i+1}/{len(chunk_ids)} (ID: {chunk_id})")
        
        try:
            result = process_chunk(chunk_id)
            if result:
                successful += 1
                logger.info(f"✅ Successfully processed chunk {chunk_id} in {time.time() - chunk_start:.2f}s")
            else:
                failed += 1
                logger.error(f"❌ Failed to process chunk {chunk_id}")
        except Exception as e:
            failed += 1
            logger.exception(f"Error processing chunk {chunk_id}: {e}")
    
    # Print summary
    total_time = time.time() - start_time
    logger.info(f"Batch processing completed in {total_time:.2f}s")
    logger.info(f"Results: {successful} successful, {failed} failed")
    
    # Check progress
    from check_progress import check_progress
    check_progress()

def main():
    parser = argparse.ArgumentParser(description="Batch process multiple chunks")
    parser.add_argument("--num-chunks", type=int, default=5,
                        help="Number of chunks to process in this batch")
    args = parser.parse_args()
    
    with app.app_context():
        batch_process_chunks(args.num_chunks)

if __name__ == "__main__":
    main()