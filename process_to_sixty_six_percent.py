#!/usr/bin/env python3
"""
Process chunks until we reach 66% completion.
This script is designed to be run in a terminal and will keep processing 
chunks until the target percentage is reached.
"""

import os
import sys
import time
import logging
from typing import Dict, Any, List, Optional
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the current directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.vector_store import VectorStore
from app import app, db
from models import DocumentChunk

# Initialize vector store
vector_store = VectorStore()

def get_db_session():
    """Get a database session."""
    from app import app
    with app.app_context():
        return db.session

def get_progress() -> Dict[str, Any]:
    """Get current progress of vector rebuild."""
    # Initialize session
    from app import app
    with app.app_context():
        # Get total chunks in database
        total_chunks = db.session.query(DocumentChunk).count()
        
        # Get total documents in vector store
        vector_docs = len(vector_store.documents)
        
        # Calculate progress
        progress = {
            "total_chunks": total_chunks,
            "vector_docs": vector_docs,
            "percentage": round((vector_docs / total_chunks) * 100, 1) if total_chunks > 0 else 0,
            "remaining": total_chunks - vector_docs
        }
        
    return progress

def get_next_chunk_ids(limit: int = 5) -> List[int]:
    """
    Get the next chunk IDs to process.
    
    Args:
        limit (int): Maximum number of chunk IDs to return
        
    Returns:
        List[int]: List of chunk IDs to process
    """
    # Get all processed chunk IDs from vector store
    processed_ids = set()
    for doc in vector_store.documents:
        if 'chunk_id' in doc.metadata:
            try:
                chunk_id = int(doc.metadata['chunk_id'])
                processed_ids.add(chunk_id)
            except (ValueError, TypeError):
                pass
    
    # Get unprocessed chunks from database
    from app import app
    with app.app_context():
        chunks = db.session.query(DocumentChunk.id).filter(
            ~DocumentChunk.id.in_(processed_ids) if processed_ids else True
        ).order_by(DocumentChunk.id).limit(limit).all()
        
        chunk_ids = [chunk[0] for chunk in chunks]
        
    return chunk_ids

def process_chunk(chunk_id: int) -> bool:
    """
    Process a single chunk using direct_process_chunk.py
    
    Args:
        chunk_id (int): ID of the chunk to process
        
    Returns:
        bool: True if processing was successful, False otherwise
    """
    try:
        cmd = f"python direct_process_chunk.py {chunk_id}"
        result = os.system(cmd)
        return result == 0
    except Exception as e:
        logger.error(f"Error processing chunk {chunk_id}: {e}")
        return False

def main():
    """Main function to process chunks until target percentage is reached."""
    target_percentage = 66.0
    logger.info(f"Starting to process chunks until {target_percentage}% completion")
    
    # Get initial progress
    progress = get_progress()
    logger.info(f"Initial progress: {progress['percentage']}% ({progress['vector_docs']}/{progress['total_chunks']} chunks)")
    
    # Process chunks until target percentage is reached
    while progress['percentage'] < target_percentage:
        # Get next chunk IDs
        chunk_ids = get_next_chunk_ids(limit=1)
        
        if not chunk_ids:
            logger.info("No more chunks to process")
            break
        
        # Process each chunk
        for chunk_id in chunk_ids:
            logger.info(f"Processing chunk {chunk_id}...")
            success = process_chunk(chunk_id)
            
            if success:
                logger.info(f"Successfully processed chunk {chunk_id}")
            else:
                logger.error(f"Failed to process chunk {chunk_id}")
                
            # Update progress
            progress = get_progress()
            logger.info(f"Current progress: {progress['percentage']}% ({progress['vector_docs']}/{progress['total_chunks']} chunks)")
            
            # Check if target percentage is reached
            if progress['percentage'] >= target_percentage:
                logger.info(f"Target percentage of {target_percentage}% reached!")
                return
            
            # Sleep briefly to avoid hammering the API
            time.sleep(1)
    
    logger.info(f"Final progress: {progress['percentage']}% ({progress['vector_docs']}/{progress['total_chunks']} chunks)")
    logger.info("Done!")

if __name__ == "__main__":
    main()