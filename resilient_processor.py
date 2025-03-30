#!/usr/bin/env python3
"""
Resilient Chunk Processor - Enhanced for Replit Environment

This script is designed to process chunks reliably in Replit's resource-constrained environment.
It implements:
1. Super small batch sizes (1-2 chunks at a time)
2. Aggressive checkpointing after each chunk
3. Progressive delays to avoid rate limiting
4. Proper error recovery
5. Detailed progress reporting
"""

import os
import sys
import time
import pickle
import logging
import datetime
import argparse
import traceback
from typing import Dict, Any, List, Set, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"logs/resilient_processor_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    ]
)
logger = logging.getLogger(__name__)

# Add the current directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import DocumentChunk
from utils.vector_store import VectorStore

# Constants
CHECKPOINT_FILE = "processed_chunk_ids.checkpoint"
DEFAULT_TARGET_PERCENTAGE = 75.0
DEFAULT_BATCH_SIZE = 1  # Process one at a time for maximum reliability
DEFAULT_DELAY_SECONDS = 2
MAX_RETRIES = 3
SAVE_EVERY_N_CHUNKS = 1  # Save after every chunk for maximum reliability

# Ensure log directory exists
os.makedirs("logs", exist_ok=True)

def save_checkpoint(processed_chunk_ids: Set[int]) -> None:
    """Save the set of processed chunk IDs to a checkpoint file."""
    try:
        with open(CHECKPOINT_FILE, 'wb') as f:
            pickle.dump(processed_chunk_ids, f)
        logger.info(f"Checkpoint saved with {len(processed_chunk_ids)} processed chunk IDs")
    except Exception as e:
        logger.error(f"Error saving checkpoint: {str(e)}")

def load_checkpoint() -> Set[int]:
    """Load the set of processed chunk IDs from a checkpoint file."""
    if not os.path.exists(CHECKPOINT_FILE):
        logger.info("No checkpoint file found, starting fresh")
        return set()
    
    try:
        with open(CHECKPOINT_FILE, 'rb') as f:
            processed_chunk_ids = pickle.load(f)
        logger.info(f"Loaded checkpoint with {len(processed_chunk_ids)} processed chunk IDs")
        return processed_chunk_ids
    except Exception as e:
        logger.error(f"Error loading checkpoint: {str(e)}")
        return set()

def get_processed_chunk_ids(vector_store: VectorStore) -> Set[int]:
    """Get the IDs of chunks that have already been processed."""
    processed_ids = vector_store.get_processed_chunk_ids()
    logger.info(f"Found {len(processed_ids)} processed chunk IDs in vector store")
    return processed_ids

def get_progress(vector_store: VectorStore, processed_chunk_ids: Set[int]) -> Dict[str, Any]:
    """Get current progress information."""
    with app.app_context():
        # Get total chunks in database
        total_chunks = db.session.query(DocumentChunk).count()
        
        # Get processed chunks count
        processed_count = len(processed_chunk_ids)
        
        # Calculate percentages
        percentage = round((processed_count / total_chunks) * 100, 1) if total_chunks > 0 else 0
        
        return {
            "total_chunks": total_chunks,
            "processed_chunks": processed_count,
            "percentage": percentage,
            "remaining_chunks": total_chunks - processed_count,
        }

def get_next_chunk_batch(batch_size: int, processed_chunk_ids: Set[int]) -> List[DocumentChunk]:
    """Get the next batch of unprocessed chunks."""
    with app.app_context():
        chunks = db.session.query(DocumentChunk).filter(
            ~DocumentChunk.id.in_(processed_chunk_ids) if processed_chunk_ids else True
        ).order_by(DocumentChunk.id).limit(batch_size).all()
        
        # Eager load the document relationship to avoid detached session issues
        for chunk in chunks:
            db.session.refresh(chunk)
            _ = chunk.document  # Force load the relationship
            
        return chunks

def process_chunk(vector_store: VectorStore, chunk: DocumentChunk) -> bool:
    """Process a single chunk and add it to the vector store."""
    try:
        # Extract safe values to avoid session detachment issues
        chunk_id = chunk.id
        document_id = chunk.document_id
        chunk_index = chunk.chunk_index
        text_content = chunk.text_content
        
        # Safe document properties
        document_filename = ""
        document_title = ""
        formatted_citation = None
        document_doi = None
        
        # Extract document properties safely
        if hasattr(chunk, 'document') and chunk.document:
            document = chunk.document
            document_filename = document.filename or ""
            document_title = document.title or ""
            
            if hasattr(document, 'formatted_citation'):
                formatted_citation = document.formatted_citation
                
            if hasattr(document, 'doi'):
                document_doi = document.doi
        
        # Create metadata
        metadata = {
            "chunk_id": chunk_id,
            "db_id": chunk_id,  # Include both for compatibility
            "document_id": document_id,
            "source_type": "pdf",  # Default value
            "chunk_index": chunk_index,
            "filename": document_filename,
            "title": document_title
        }
        
        # Add citation information if available
        if formatted_citation:
            metadata["citation"] = formatted_citation
        if document_doi:
            metadata["doi"] = document_doi
        
        # Add to vector store
        vector_store.add_text(text_content, metadata=metadata)
        
        return True
    except Exception as e:
        logger.error(f"Error processing chunk {chunk.id}: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def process_batch(vector_store: VectorStore, chunks: List[DocumentChunk], 
                 processed_chunk_ids: Set[int]) -> Dict[str, Any]:
    """Process a batch of chunks with careful error handling."""
    results = {
        "total": len(chunks),
        "successful": 0,
        "failed": 0,
        "chunk_ids_processed": [],
        "failed_chunk_ids": []
    }
    
    for i, chunk in enumerate(chunks):
        logger.info(f"Processing chunk {chunk.id} ({i+1}/{len(chunks)})")
        
        # Try with retries
        success = False
        attempts = 0
        
        while not success and attempts < MAX_RETRIES:
            attempts += 1
            if attempts > 1:
                logger.info(f"Retry {attempts}/{MAX_RETRIES} for chunk {chunk.id}")
                time.sleep(1)  # Short delay before retry
                
            success = process_chunk(vector_store, chunk)
        
        if success:
            results["successful"] += 1
            results["chunk_ids_processed"].append(chunk.id)
            processed_chunk_ids.add(chunk.id)
            logger.info(f"Successfully processed chunk {chunk.id}")
            
            # Save after every few chunks for maximum reliability
            if results["successful"] % SAVE_EVERY_N_CHUNKS == 0:
                vector_store.save()
                save_checkpoint(processed_chunk_ids)
                logger.info(f"Saved vector store and checkpoint after processing chunk {chunk.id}")
        else:
            results["failed"] += 1
            results["failed_chunk_ids"].append(chunk.id)
            logger.error(f"Failed to process chunk {chunk.id} after {MAX_RETRIES} attempts")
    
    # Final save after the batch
    if results["successful"] > 0:
        vector_store.save()
        save_checkpoint(processed_chunk_ids)
    
    return results

def resilient_processor(batch_size: int = DEFAULT_BATCH_SIZE,
                       target_percentage: float = DEFAULT_TARGET_PERCENTAGE,
                       delay_seconds: int = DEFAULT_DELAY_SECONDS) -> None:
    """
    Process chunks in a highly resilient way until target percentage is reached.
    
    Args:
        batch_size: Number of chunks to process per batch (keep very small for reliability)
        target_percentage: Target percentage of completion
        delay_seconds: Delay between chunks in seconds
    """
    logger.info(f"Running resilient_processor.py with batch size {batch_size}")
    logger.info(f"Process started with PID: {os.getpid()}")
    logger.info(f"Starting chunk processing to {target_percentage}% completion")
    logger.info(f"Using batch size of {batch_size} with {delay_seconds}s delay")
    
    # Initialize vector store
    vector_store = VectorStore()
    
    # Load checkpoint and combine with vector store IDs
    checkpoint_ids = load_checkpoint()
    vector_store_ids = get_processed_chunk_ids(vector_store)
    processed_chunk_ids = checkpoint_ids.union(vector_store_ids)
    logger.info(f"Total processed IDs after combining checkpoint and vector store: {len(processed_chunk_ids)}")
    
    # Get initial progress
    progress = get_progress(vector_store, processed_chunk_ids)
    logger.info(f"Vector store:   {progress['processed_chunks']} chunks")
    logger.info(f"Database:       {progress['total_chunks']} chunks in total")
    logger.info(f"----------------------------------------")
    logger.info(f"Progress:       {progress['processed_chunks']}/{progress['total_chunks']} chunks")
    logger.info(f"                {progress['percentage']}% complete")
    logger.info(f"Remaining:      {progress['remaining_chunks']} chunks")
    logger.info(f"Est. time:      {formatted_time_estimate(progress['remaining_chunks'], batch_size, delay_seconds)}")
    logger.info(f"========================================")
    
    # Process batches until target reached
    batch_num = 1
    
    while progress["percentage"] < target_percentage:
        # Get the next batch of chunks to process
        chunks = get_next_chunk_batch(batch_size, processed_chunk_ids)
        
        if not chunks:
            logger.info("No more chunks to process")
            break
        
        logger.info(f"Processing batch #{batch_num} with {len(chunks)} chunks")
        
        # Process the batch
        results = process_batch(vector_store, chunks, processed_chunk_ids)
        
        # Log results
        logger.info(f"Processed {results['successful']}/{results['total']} chunks in batch #{batch_num}")
        
        if results["failed"] > 0:
            logger.warning(f"Failed to process {results['failed']} chunks in batch #{batch_num}")
            logger.warning(f"Failed chunk IDs: {results['failed_chunk_ids']}")
        
        # Check progress
        progress = get_progress(vector_store, processed_chunk_ids)
        logger.info(f"Vector store:   {progress['processed_chunks']} chunks")
        logger.info(f"Database:       {progress['total_chunks']} chunks in total")
        logger.info(f"----------------------------------------")
        logger.info(f"Progress:       {progress['processed_chunks']}/{progress['total_chunks']} chunks")
        logger.info(f"                {progress['percentage']}% complete")
        logger.info(f"Remaining:      {progress['remaining_chunks']} chunks")
        logger.info(f"Est. time:      {formatted_time_estimate(progress['remaining_chunks'], batch_size, delay_seconds)}")
        logger.info(f"========================================")
        
        # Check if target reached
        if progress["percentage"] >= target_percentage:
            logger.info(f"Target percentage of {target_percentage}% reached!")
            break
        
        # Wait between batches with a progressive delay to avoid rate limits
        delay = delay_seconds + (batch_num * 0.1)  # Slight increase in delay over time
        logger.info(f"Waiting {delay:.1f} seconds before next batch...")
        time.sleep(delay)
        
        batch_num += 1
    
    # Final progress update
    progress = get_progress(vector_store, processed_chunk_ids)
    logger.info(f"Processing completed. Final progress: {progress['percentage']}%")
    logger.info(f"Processed {progress['processed_chunks']}/{progress['total_chunks']} chunks")

def formatted_time_estimate(remaining_chunks: int, batch_size: int, delay_seconds: int) -> str:
    """Format the estimated time remaining in a human-readable format."""
    # Estimate time per chunk (processing + delay)
    time_per_chunk = delay_seconds + 1  # Assume 1 second for processing per chunk
    
    # Calculate total estimated seconds
    total_seconds = (remaining_chunks // batch_size) * (time_per_chunk * batch_size)
    if remaining_chunks % batch_size > 0:
        total_seconds += (remaining_chunks % batch_size) * time_per_chunk
    
    # Format time string
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m {seconds}s"

def main():
    """Main function to parse arguments and start processing."""
    parser = argparse.ArgumentParser(description='Process chunks until target percentage reached')
    parser.add_argument('--target', type=float, default=DEFAULT_TARGET_PERCENTAGE,
                      help=f'Target percentage to reach (default: {DEFAULT_TARGET_PERCENTAGE})')
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE,
                      help=f'Number of chunks to process per batch (default: {DEFAULT_BATCH_SIZE})')
    parser.add_argument('--delay', type=int, default=DEFAULT_DELAY_SECONDS,
                      help=f'Delay between batches in seconds (default: {DEFAULT_DELAY_SECONDS})')
    
    args = parser.parse_args()
    
    resilient_processor(
        batch_size=args.batch_size,
        target_percentage=args.target, 
        delay_seconds=args.delay
    )

if __name__ == "__main__":
    main()