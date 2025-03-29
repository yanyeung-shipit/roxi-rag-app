#!/usr/bin/env python3
"""
Parallel Chunk Processor

This script processes multiple chunks in parallel to rebuild the vector store
faster while working within Replit's constraints. It uses checkpointing to
track progress and can resume processing after timeout or interruption.

Usage:
    python parallel_chunk_processor.py [--batch-size BATCH_SIZE] [--max-chunks MAX_CHUNKS]
"""

import argparse
import json
import logging
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

import numpy as np
from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import sessionmaker

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

# Constants
CHECKPOINT_DIR = Path("./logs/checkpoints")
CHECKPOINT_FILE = CHECKPOINT_DIR / "parallel_processor_checkpoint.json"
OPENAI_API_RATE_LIMIT = 3  # seconds between embedding calls

# Initialize vector store
vector_store = VectorStore()

def setup_checkpoint_directory() -> None:
    """Create the checkpoint directory if it doesn't exist."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

def save_checkpoint(processed_chunks: Set[int], 
                    remaining_chunks: List[int], 
                    last_processed_time: float,
                    successful_chunks: int, 
                    failed_chunks: int) -> None:
    """
    Save a checkpoint of processing progress.
    
    Args:
        processed_chunks: Set of chunk IDs that have been processed
        remaining_chunks: List of chunk IDs still to be processed
        last_processed_time: Timestamp of last processing
        successful_chunks: Count of successfully processed chunks
        failed_chunks: Count of chunks that failed to process
    """
    checkpoint_data = {
        "processed_chunks": list(processed_chunks),
        "remaining_chunks": remaining_chunks,
        "last_processed_time": last_processed_time,
        "successful_chunks": successful_chunks,
        "failed_chunks": failed_chunks,
        "timestamp": datetime.now().isoformat()
    }
    
    with CHECKPOINT_FILE.open('w') as f:
        json.dump(checkpoint_data, f)
    
    logger.info(f"Checkpoint saved: {successful_chunks} successful, {failed_chunks} failed")

def load_checkpoint() -> Optional[Dict]:
    """
    Load the processing checkpoint if it exists.
    
    Returns:
        Dict or None: Checkpoint data or None if no checkpoint exists
    """
    if not CHECKPOINT_FILE.exists():
        logger.info("No checkpoint file found, starting fresh")
        return None
    
    try:
        with CHECKPOINT_FILE.open('r') as f:
            checkpoint_data = json.load(f)
            
        logger.info(f"Loaded checkpoint from {checkpoint_data.get('timestamp')}")
        logger.info(f"Previously processed {len(checkpoint_data.get('processed_chunks', []))} chunks")
        return checkpoint_data
    except Exception as e:
        logger.error(f"Error loading checkpoint: {e}")
        return None

def get_all_chunk_ids() -> List[int]:
    """
    Get all chunk IDs from the database that need to be processed.
    
    Returns:
        List of chunk IDs
    """
    with app.app_context():
        chunks = DocumentChunk.query.order_by(DocumentChunk.id).all()
        return [chunk.id for chunk in chunks]

def get_next_chunk_batch(remaining_chunks: List[int], batch_size: int) -> List[int]:
    """
    Get the next batch of chunk IDs to process.
    
    Args:
        remaining_chunks: List of all remaining chunk IDs
        batch_size: Number of chunks to include in the batch
    
    Returns:
        List of chunk IDs for the next batch
    """
    batch_size = min(batch_size, len(remaining_chunks))
    batch = remaining_chunks[:batch_size]
    return batch

def process_chunk(chunk_id: int) -> bool:
    """
    Process a single chunk and add it to the vector store.
    
    Args:
        chunk_id: ID of the chunk to process
    
    Returns:
        bool: True if successful, False otherwise
    """
    with app.app_context():
        try:
            # Get the chunk from the database
            chunk = DocumentChunk.query.get(chunk_id)
            if not chunk:
                logger.error(f"Chunk {chunk_id} not found in database")
                return False
            
            # Get the document the chunk belongs to
            document = Document.query.get(chunk.document_id)
            if not document:
                logger.error(f"Document {chunk.document_id} not found for chunk {chunk_id}")
                return False
            
            logger.info(f"Processing chunk {chunk_id} from document {chunk.document_id}: {document.filename}")
            
            # Extract text and metadata
            text = chunk.text_content
            metadata = {
                "chunk_id": chunk.id,
                "document_id": document.id,
                "filename": document.filename,
                "page_number": chunk.page_number,
                "chunk_index": chunk.chunk_index,
                "doi": document.doi,
                "authors": document.authors,
                "journal": document.journal,
                "publication_year": document.publication_year,
                "formatted_citation": document.formatted_citation
            }
            
            # Add to vector store
            vector_store.add_texts([text], [metadata])
            vector_store.save()
            
            # Add a small delay to avoid rate limits
            time.sleep(random.uniform(0.5, 1.0))
            
            return True
        except Exception as e:
            logger.error(f"Error processing chunk {chunk_id}: {e}")
            return False

def process_chunk_batch(batch: List[int], processed_chunks: Set[int]) -> Tuple[List[int], List[int]]:
    """
    Process a batch of chunks and return the results.
    
    Args:
        batch: List of chunk IDs to process
        processed_chunks: Set of already processed chunk IDs
    
    Returns:
        Tuple of (successful_ids, failed_ids)
    """
    successful = []
    failed = []
    
    for chunk_id in batch:
        if chunk_id in processed_chunks:
            logger.info(f"Chunk {chunk_id} already processed, skipping")
            continue
        
        # Add a delay between chunks to avoid rate limits
        time.sleep(OPENAI_API_RATE_LIMIT)
        
        success = process_chunk(chunk_id)
        if success:
            successful.append(chunk_id)
            processed_chunks.add(chunk_id)
            logger.info(f"Successfully processed chunk {chunk_id}")
        else:
            failed.append(chunk_id)
            logger.error(f"Failed to process chunk {chunk_id}")
    
    return successful, failed

def calculate_progress_stats(processed_chunks: Set[int], total_chunks: int) -> Dict:
    """
    Calculate and return progress statistics.
    
    Args:
        processed_chunks: Set of processed chunk IDs
        total_chunks: Total number of chunks to process
    
    Returns:
        Dict with progress statistics
    """
    processed_count = len(processed_chunks)
    percent_complete = round(processed_count / total_chunks * 100, 1) if total_chunks > 0 else 0
    remaining = total_chunks - processed_count
    est_time_mins = round(remaining * OPENAI_API_RATE_LIMIT / 60, 1)
    
    return {
        "processed_count": processed_count,
        "total_chunks": total_chunks,
        "percent_complete": percent_complete,
        "remaining": remaining,
        "est_time_mins": est_time_mins
    }

def print_progress_bar(percent_complete: float, width: int = 50) -> None:
    """
    Print a progress bar to the console.
    
    Args:
        percent_complete: Percentage complete (0-100)
        width: Width of the progress bar in characters
    """
    filled_width = int(width * percent_complete / 100)
    bar = '█' * filled_width + '░' * (width - filled_width)
    logger.info(f"Progress: |{bar}| {percent_complete}%")

def main():
    """Main function to process chunks in parallel"""
    parser = argparse.ArgumentParser(description="Process chunks in parallel to rebuild vector store")
    parser.add_argument("--batch-size", type=int, default=5, 
                      help="Number of chunks to process in each batch")
    parser.add_argument("--max-chunks", type=int, default=None,
                      help="Maximum number of chunks to process in this run")
    args = parser.parse_args()
    
    # Set up the checkpoint directory
    setup_checkpoint_directory()
    
    # Load checkpoint if it exists
    checkpoint = load_checkpoint()
    
    # Initialize tracking variables
    if checkpoint:
        processed_chunks = set(checkpoint.get("processed_chunks", []))
        remaining_chunks = checkpoint.get("remaining_chunks", [])
        successful_chunks = checkpoint.get("successful_chunks", 0)
        failed_chunks = checkpoint.get("failed_chunks", 0)
        last_processed_time = checkpoint.get("last_processed_time", time.time())
    else:
        # Get all chunks that need processing
        all_chunk_ids = get_all_chunk_ids()
        processed_chunks = set()
        remaining_chunks = all_chunk_ids
        successful_chunks = 0
        failed_chunks = 0
        last_processed_time = time.time()
    
    total_chunks = len(processed_chunks) + len(remaining_chunks)
    
    logger.info(f"Starting parallel processing with batch size: {args.batch_size}")
    logger.info(f"Total chunks to process: {total_chunks}")
    logger.info(f"Already processed: {len(processed_chunks)} chunks")
    logger.info(f"Remaining: {len(remaining_chunks)} chunks")
    
    # Limit the number of chunks to process if specified
    if args.max_chunks is not None:
        max_to_process = min(args.max_chunks, len(remaining_chunks))
        remaining_chunks = remaining_chunks[:max_to_process]
        logger.info(f"Limited to processing {max_to_process} chunks this run")
    
    batch_count = 0
    start_time = time.time()
    
    # Process chunks in batches until none are left
    while remaining_chunks:
        batch_count += 1
        batch = get_next_chunk_batch(remaining_chunks, args.batch_size)
        
        logger.info(f"Processing batch {batch_count} with {len(batch)} chunks")
        
        # Process the batch
        successful_batch, failed_batch = process_chunk_batch(batch, processed_chunks)
        
        # Update counts
        successful_chunks += len(successful_batch)
        failed_chunks += len(failed_batch)
        
        # Remove processed chunks from the remaining list
        for chunk_id in batch:
            if chunk_id in remaining_chunks:
                remaining_chunks.remove(chunk_id)
        
        # Save checkpoint after each batch
        last_processed_time = time.time()
        save_checkpoint(processed_chunks, remaining_chunks, last_processed_time,
                       successful_chunks, failed_chunks)
        
        # Calculate and display progress
        progress_stats = calculate_progress_stats(processed_chunks, total_chunks)
        print_progress_bar(progress_stats["percent_complete"])
        logger.info(f"Processed {progress_stats['processed_count']}/{progress_stats['total_chunks']} "
                   f"chunks ({progress_stats['percent_complete']}% complete)")
        logger.info(f"Estimated time remaining: {progress_stats['est_time_mins']} minutes")
        
        # Check if we've processed enough chunks for this run
        if args.max_chunks is not None and successful_chunks >= args.max_chunks:
            logger.info(f"Reached max chunks limit ({args.max_chunks}), stopping")
            break
    
    # Final report
    elapsed_time = time.time() - start_time
    elapsed_mins = elapsed_time / 60
    logger.info(f"Completed processing in {elapsed_mins:.2f} minutes")
    logger.info(f"Successfully processed {successful_chunks} chunks")
    logger.info(f"Failed to process {failed_chunks} chunks")
    
    # Calculate final progress
    final_stats = calculate_progress_stats(processed_chunks, total_chunks)
    logger.info(f"Overall progress: {final_stats['percent_complete']}% complete")
    
    if remaining_chunks:
        logger.info(f"There are {len(remaining_chunks)} chunks remaining to process")
    else:
        logger.info("All chunks have been processed!")

if __name__ == "__main__":
    main()