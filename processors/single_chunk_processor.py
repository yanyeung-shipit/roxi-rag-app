#!/usr/bin/env python3
"""
Single-Chunk Processor

This script processes exactly one chunk, then exits completely.
It's designed to be extremely conservative with system resources.
It will be scheduled to run periodically by an external scheduler.

Usage:
python processors/single_chunk_processor.py

Features:
- Loads minimal dependencies
- Processes exactly one chunk
- Exits completely after processing
- Updates checkpoint to track progress
- Detailed logging
"""

import os
import sys
import pickle
import logging
import time
import argparse
from datetime import datetime
import json
from typing import Dict, Any, Set, List, Optional, Union, Tuple

# Set up logging
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
log_file = os.path.join(LOG_DIR, "single_chunk_processor.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Constants
CHECKPOINT_DIR = os.path.join(LOG_DIR, "checkpoints")
CHECKPOINT_FILE = os.path.join(CHECKPOINT_DIR, "adaptive_processor_checkpoint.pkl")
TARGET_PERCENTAGE = 100.0  # Default target percentage

def save_checkpoint(processed_chunk_ids: Set[int], chunk_id: int, document_id: int) -> None:
    """
    Save current processing state to checkpoint.
    
    Args:
        processed_chunk_ids (Set[int]): Set of processed chunk IDs
        chunk_id (int): Current chunk ID
        document_id (int): Current document ID
    """
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    
    checkpoint_data = {
        "processed_chunk_ids": processed_chunk_ids,
        "last_chunk_id": chunk_id,
        "last_document_id": document_id,
        "timestamp": datetime.now().isoformat()
    }
    
    with open(CHECKPOINT_FILE, "wb") as f:
        pickle.dump(checkpoint_data, f)
    
    logger.info(f"Checkpoint saved. Total processed: {len(processed_chunk_ids)} chunks")

def load_checkpoint() -> Dict[str, Any]:
    """
    Load checkpoint data.
    
    Returns:
        Dict[str, Any]: Checkpoint data or empty dictionary if no checkpoint
    """
    if not os.path.exists(CHECKPOINT_FILE):
        logger.info("No checkpoint file found. Starting fresh.")
        return {
            "processed_chunk_ids": set(),
            "last_chunk_id": 0,
            "last_document_id": 0,
            "timestamp": datetime.now().isoformat()
        }
    
    try:
        with open(CHECKPOINT_FILE, "rb") as f:
            checkpoint_data = pickle.load(f)
            logger.info(f"Loaded checkpoint from {checkpoint_data.get('timestamp', 'unknown')}") 
            logger.info(f"Checkpoint contains {len(checkpoint_data.get('processed_chunk_ids', []))} processed chunk IDs")
            return checkpoint_data
    except Exception as e:
        logger.error(f"Error loading checkpoint: {e}")
        return {
            "processed_chunk_ids": set(),
            "last_chunk_id": 0, 
            "last_document_id": 0,
            "timestamp": datetime.now().isoformat()
        }

def get_database_stats() -> Dict[str, Any]:
    """
    Get database statistics.
    
    Returns:
        Dict[str, Any]: Database statistics
    """
    # Import here to minimize memory usage at startup
    from utils.database import get_db_session, Document, DocumentChunk
    
    db = get_db_session()
    try:
        # Get document and chunk counts
        doc_count = db.query(Document).count()
        chunk_count = db.query(DocumentChunk).count()
        
        # Get chunks by document type
        chunks_by_type = {}
        for doc_type in ["pdf", "website"]:
            count = db.query(DocumentChunk).join(Document).filter(
                Document.doc_type == doc_type
            ).count()
            if count > 0:
                chunks_by_type[doc_type] = count
        
        return {
            "total_documents": doc_count,
            "total_chunks": chunk_count,
            "chunks_by_type": chunks_by_type
        }
    finally:
        db.close()

def process_single_chunk() -> Dict[str, Any]:
    """
    Process a single chunk from the database.
    
    Returns:
        Dict[str, Any]: Processing result information
    """
    # Import here to minimize memory usage at startup
    import gc
    from utils.database import get_db_session, DocumentChunk
    from utils.vector_store import add_chunk_to_vector_store
    
    result = {
        "success": False,
        "chunk_id": None,
        "document_id": None,
        "error": None,
        "total_processed": 0
    }
    
    # Load checkpoint
    checkpoint = load_checkpoint()
    processed_chunk_ids = checkpoint.get("processed_chunk_ids", set())
    result["total_processed"] = len(processed_chunk_ids)
    
    # Get database stats
    db_stats = get_database_stats()
    total_chunks = db_stats.get("total_chunks", 0)
    
    # Check if we've already reached the target
    if total_chunks > 0:
        current_percentage = (len(processed_chunk_ids) / total_chunks) * 100
        logger.info(f"Current progress: {current_percentage:.1f}% ({len(processed_chunk_ids)}/{total_chunks} chunks)")
        
        if current_percentage >= TARGET_PERCENTAGE:
            logger.info(f"Target of {TARGET_PERCENTAGE}% already reached! Current progress: {current_percentage:.1f}%")
            result["success"] = True
            result["message"] = "Target already reached"
            return result
    
    # Find an unprocessed chunk
    db = get_db_session()
    try:
        # Get the next unprocessed chunk
        chunk = db.query(DocumentChunk).filter(
            ~DocumentChunk.id.in_(processed_chunk_ids)
        ).order_by(DocumentChunk.id).first()
        
        if not chunk:
            logger.info("No more unprocessed chunks found.")
            result["success"] = True
            result["message"] = "No more chunks to process"
            return result
        
        # Process the chunk
        logger.info(f"Processing chunk {chunk.id} from document {chunk.document_id}")
        
        try:
            # Add to vector store
            success = add_chunk_to_vector_store(chunk)
            
            if success:
                # Update checkpoint
                processed_chunk_ids.add(chunk.id)
                save_checkpoint(processed_chunk_ids, chunk.id, chunk.document_id)
                
                # Update result
                result["success"] = True
                result["chunk_id"] = chunk.id
                result["document_id"] = chunk.document_id
                result["total_processed"] = len(processed_chunk_ids)
                
                # Calculate new progress
                if total_chunks > 0:
                    new_percentage = (len(processed_chunk_ids) / total_chunks) * 100
                    logger.info(f"New progress: {new_percentage:.1f}% ({len(processed_chunk_ids)}/{total_chunks} chunks)")
                    
                    if new_percentage >= TARGET_PERCENTAGE:
                        logger.info(f"Target of {TARGET_PERCENTAGE}% reached! Current progress: {new_percentage:.1f}%")
            else:
                logger.error(f"Failed to add chunk {chunk.id} to vector store")
                result["error"] = "Failed to add chunk to vector store"
        except Exception as e:
            logger.exception(f"Error processing chunk {chunk.id}: {e}")
            result["error"] = str(e)
    finally:
        db.close()
    
    # Force garbage collection
    gc.collect()
    
    return result

def main():
    """Main function."""
    global TARGET_PERCENTAGE
    
    parser = argparse.ArgumentParser(description="Process a single document chunk")
    parser.add_argument("--target", type=float, default=TARGET_PERCENTAGE,
                        help=f"Target completion percentage (default: {TARGET_PERCENTAGE}%)")
    args = parser.parse_args()
    
    TARGET_PERCENTAGE = args.target
    
    logger.info(f"Single-chunk processor started with target: {TARGET_PERCENTAGE}%")
    
    start_time = time.time()
    result = process_single_chunk()
    elapsed_time = time.time() - start_time
    
    if result["success"]:
        if result.get("chunk_id"):
            logger.info(f"Successfully processed chunk {result['chunk_id']} in {elapsed_time:.2f} seconds")
        else:
            logger.info(f"No chunk processed: {result.get('message', 'Unknown reason')}")
    else:
        logger.error(f"Failed to process chunk: {result.get('error', 'Unknown error')}")
    
    logger.info("Single-chunk processor finished")
    return result

if __name__ == "__main__":
    main()