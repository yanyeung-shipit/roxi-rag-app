#!/usr/bin/env python3
"""
Find unprocessed chunks by comparing database chunks to vector store.
This script outputs a list of chunk IDs that need to be processed.

Usage:
    python find_unprocessed_chunks.py [--limit LIMIT] [--output FILE]
"""

import argparse
import json
import sys
import logging
from typing import List, Set

from app import app, db
from models import Document, DocumentChunk
from utils.vector_store import VectorStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def get_processed_chunk_ids() -> Set[int]:
    """
    Get IDs of chunks that have already been processed and added to the vector store.
    
    Returns:
        Set[int]: Set of processed chunk IDs
    """
    # Initialize vector store
    vector_store = VectorStore()
    
    # Get processed chunks from vector store
    processed_chunk_ids = set()
    for doc in vector_store.documents:
        if isinstance(doc, dict):
            metadata = doc.get("metadata", {})
            chunk_id = metadata.get("chunk_id")
            if chunk_id:
                processed_chunk_ids.add(int(chunk_id))
        elif hasattr(doc, "metadata") and isinstance(doc.metadata, dict):
            chunk_id = doc.metadata.get("chunk_id")
            if chunk_id:
                processed_chunk_ids.add(int(chunk_id))
    
    return processed_chunk_ids

def get_all_chunk_ids() -> List[int]:
    """
    Get all chunk IDs from the database.
    
    Returns:
        List[int]: List of all chunk IDs in the database
    """
    with app.app_context():
        all_chunks = DocumentChunk.query.order_by(DocumentChunk.id).all()
        return [chunk.id for chunk in all_chunks]

def find_unprocessed_chunks(limit: int = None) -> List[int]:
    """
    Find chunks that exist in the database but not in the vector store.
    
    Args:
        limit (int, optional): Maximum number of chunk IDs to return
        
    Returns:
        List[int]: List of unprocessed chunk IDs
    """
    # Get all chunks from database
    all_chunk_ids = get_all_chunk_ids()
    
    # Get processed chunks from vector store
    processed_chunk_ids = get_processed_chunk_ids()
    
    # Find unprocessed chunks
    unprocessed_chunk_ids = list(set(all_chunk_ids) - processed_chunk_ids)
    unprocessed_chunk_ids.sort()  # Sort by ID, which is often by document and page
    
    # Apply limit if specified
    if limit and limit > 0:
        unprocessed_chunk_ids = unprocessed_chunk_ids[:limit]
    
    return unprocessed_chunk_ids

def main():
    parser = argparse.ArgumentParser(description="Find unprocessed chunks")
    parser.add_argument("--limit", type=int, default=None, 
                      help="Maximum number of chunks to return")
    parser.add_argument("--output", type=str, default=None,
                      help="Output file for chunk IDs (default: stdout)")
    args = parser.parse_args()
    
    # Find unprocessed chunks
    unprocessed_chunks = find_unprocessed_chunks(args.limit)
    
    # Report statistics
    total_in_db = len(get_all_chunk_ids())
    total_processed = len(get_processed_chunk_ids())
    total_unprocessed = len(find_unprocessed_chunks())
    
    logger.info(f"Total chunks in database: {total_in_db}")
    logger.info(f"Total chunks processed: {total_processed}")
    logger.info(f"Total chunks unprocessed: {total_unprocessed}")
    logger.info(f"Returning {len(unprocessed_chunks)} chunk IDs")
    
    # Output chunk IDs
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(unprocessed_chunks, f)
        logger.info(f"Wrote {len(unprocessed_chunks)} chunk IDs to {args.output}")
    else:
        # Print one per line for easy use in scripts
        for chunk_id in unprocessed_chunks:
            print(chunk_id)

if __name__ == "__main__":
    main()