#!/usr/bin/env python3
"""
Process chunks incrementally until we reach 66% completion.
This script processes chunks one by one to build up the vector store.
"""

import os
import sys
import time
import logging
from typing import Dict, Any, List

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the current directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import DocumentChunk
from utils.vector_store import VectorStore

def get_progress():
    """Get the current progress of vector store rebuilding."""
    with app.app_context():
        # Get total chunks in database
        total_chunks = db.session.query(DocumentChunk).count()
        
        # Get vector store document count
        vector_store = VectorStore()
        vector_count = len(vector_store.documents)
        
        # Calculate percentages
        percentage = round((vector_count / total_chunks) * 100, 1) if total_chunks > 0 else 0
        
        return {
            "total_chunks": total_chunks,
            "processed_chunks": vector_count,
            "percentage": percentage,
            "remaining": total_chunks - vector_count
        }

def get_next_chunk_id():
    """Get the next unprocessed chunk ID."""
    # Get processed chunk IDs
    vector_store = VectorStore()
    processed_ids = set()
    
    for doc in vector_store.documents:
        if isinstance(doc.metadata, dict) and 'chunk_id' in doc.metadata:
            try:
                chunk_id = int(doc.metadata['chunk_id'])
                processed_ids.add(chunk_id)
            except (ValueError, TypeError):
                pass
    
    # Find the next unprocessed chunk
    with app.app_context():
        chunk = db.session.query(DocumentChunk).filter(
            ~DocumentChunk.id.in_(processed_ids) if processed_ids else True
        ).order_by(DocumentChunk.id).first()
        
        if chunk:
            return chunk.id
    
    return None

def process_chunk(chunk_id):
    """Process a single chunk using direct_process_chunk.py."""
    cmd = f"python direct_process_chunk.py {chunk_id}"
    result = os.system(cmd)
    return result == 0

def process_until_target(target_percentage=66.0, max_chunks=None, delay=1):
    """
    Process chunks until reaching target percentage or max chunks.
    
    Args:
        target_percentage: Target percentage to reach
        max_chunks: Maximum number of chunks to process
        delay: Delay between processing chunks in seconds
    """
    # Get initial progress
    progress = get_progress()
    logger.info(f"Initial progress: {progress['percentage']}% "
               f"({progress['processed_chunks']}/{progress['total_chunks']} chunks)")
    
    # Initialize counters
    chunks_processed = 0
    start_time = time.time()
    
    # Process chunks until target reached or max chunks processed
    while progress['percentage'] < target_percentage:
        if max_chunks is not None and chunks_processed >= max_chunks:
            logger.info(f"Reached maximum chunks to process ({max_chunks})")
            break
        
        # Get next chunk ID
        chunk_id = get_next_chunk_id()
        if not chunk_id:
            logger.info("No more unprocessed chunks found")
            break
        
        # Process the chunk
        logger.info(f"Processing chunk {chunk_id}...")
        if process_chunk(chunk_id):
            chunks_processed += 1
            logger.info(f"Successfully processed chunk {chunk_id}")
        else:
            logger.error(f"Failed to process chunk {chunk_id}")
        
        # Update progress
        progress = get_progress()
        elapsed_time = time.time() - start_time
        rate = chunks_processed / elapsed_time if elapsed_time > 0 else 0
        est_remaining = progress['remaining'] / rate if rate > 0 else 0
        est_hours = int(est_remaining // 3600)
        est_minutes = int((est_remaining % 3600) // 60)
        
        logger.info(f"Progress: {progress['percentage']}% "
                   f"({progress['processed_chunks']}/{progress['total_chunks']} chunks)")
        logger.info(f"Rate: {rate:.2f} chunks/sec, "
                   f"Est. time remaining: {est_hours}h {est_minutes}m")
        
        # Check if target reached
        if progress['percentage'] >= target_percentage:
            logger.info(f"Target percentage of {target_percentage}% reached!")
            break
        
        # Wait a bit to avoid hammering the API
        time.sleep(delay)
    
    # Final progress
    progress = get_progress()
    logger.info(f"Final progress: {progress['percentage']}% "
               f"({progress['processed_chunks']}/{progress['total_chunks']} chunks)")
    logger.info(f"Processed {chunks_processed} chunks in this session")

if __name__ == "__main__":
    # Default to 66% target, or use command line argument
    target = 66.0
    if len(sys.argv) > 1:
        try:
            target = float(sys.argv[1])
        except ValueError:
            logger.error(f"Invalid target percentage: {sys.argv[1]}")
            sys.exit(1)
    
    max_chunks_to_process = None
    if len(sys.argv) > 2:
        try:
            max_chunks_to_process = int(sys.argv[2])
        except ValueError:
            logger.error(f"Invalid max chunks: {sys.argv[2]}")
            sys.exit(1)
    
    process_until_target(target_percentage=target, max_chunks=max_chunks_to_process)