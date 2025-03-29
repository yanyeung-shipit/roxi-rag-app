#!/usr/bin/env python
"""
Improved Continuous Chunk Processor

This script provides a robust way to continuously process chunks in the background.
Features:
- Processes chunks in batches to minimize overhead
- Maintains checkpoints for recovery
- Provides detailed logging and progress tracking
- Handles errors gracefully without stopping the entire process
- Can be interrupted and resumed
"""

import os
import sys
import time
import json
import logging
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional, Union, Set

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/continuous_processing.log')
    ]
)
logger = logging.getLogger(__name__)

# Ensure log directories exist
os.makedirs('logs', exist_ok=True)
os.makedirs('logs/checkpoints', exist_ok=True)

# Constants
CHECKPOINT_DIR = 'logs/checkpoints'
CHECKPOINT_FILE = os.path.join(CHECKPOINT_DIR, 'last_processed_chunk.json')
DEFAULT_BATCH_SIZE = 5
MAX_RETRIES = 3
DELAY_BETWEEN_CHUNKS = 1  # seconds
DELAY_BETWEEN_BATCHES = 5  # seconds

def save_checkpoint(chunk_id: int, document_id: Optional[int] = None, success: bool = True) -> None:
    """
    Save a checkpoint of the last processed chunk.
    
    Args:
        chunk_id: ID of the chunk that was processed
        document_id: ID of the document containing the chunk (if available)
        success: Whether the processing was successful
    """
    checkpoint_data = {
        'chunk_id': chunk_id,
        'document_id': document_id,
        'timestamp': datetime.now().isoformat(),
        'success': success
    }
    
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump(checkpoint_data, f, indent=2)
    
    logger.debug(f"Saved checkpoint: chunk_id={chunk_id}, success={success}")

def load_checkpoint() -> Optional[Dict[str, Any]]:
    """
    Load the last processed chunk checkpoint.
    
    Returns:
        Dictionary containing checkpoint data or None if no checkpoint exists
    """
    if not os.path.exists(CHECKPOINT_FILE):
        return None
    
    try:
        with open(CHECKPOINT_FILE, 'r') as f:
            checkpoint_data = json.load(f)
        
        logger.debug(f"Loaded checkpoint: chunk_id={checkpoint_data.get('chunk_id')}")
        return checkpoint_data
    except Exception as e:
        logger.error(f"Failed to load checkpoint: {e}")
        return None

def get_next_chunk_ids(batch_size: int = DEFAULT_BATCH_SIZE, start_from_id: Optional[int] = None) -> List[int]:
    """
    Get a list of the next chunk IDs to process.
    
    Args:
        batch_size: Maximum number of chunks to retrieve
        start_from_id: Optional ID to start from (for resuming from checkpoints)
        
    Returns:
        List of chunk IDs to process next
    """
    import sys
    sys.path.append('.')
    
    # First, try to use find_unprocessed_chunks.py if it exists
    try:
        from find_unprocessed_chunks import find_unprocessed_chunks
        
        # Get unprocessed chunks
        chunk_ids = find_unprocessed_chunks(batch_size)
        
        # If we have a start_from_id, filter the list to start from that ID
        if start_from_id is not None and chunk_ids:
            try:
                start_idx = chunk_ids.index(start_from_id)
                chunk_ids = chunk_ids[start_idx:start_idx + batch_size]
            except ValueError:
                # If start_from_id is not in the list, just use the first batch_size chunks
                chunk_ids = chunk_ids[:batch_size]
        
        # If we found any chunks, return them
        if chunk_ids:
            return chunk_ids
    except (ImportError, Exception) as e:
        logger.warning(f"Could not use find_unprocessed_chunks.py: {e}")
    
    # Fallback: Direct database query with SQLAlchemy
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
        import os
        
        # Connect to the database
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            logger.error("DATABASE_URL environment variable is not set")
            return []
        
        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # First, get IDs of chunks that exist in the vector store
        try:
            from utils.vector_store import VectorStore
            vs = VectorStore()
            processed_ids_set = set(vs.get_processed_chunk_ids())
        except Exception as e:
            logger.warning(f"Could not get processed chunk IDs from vector store: {e}")
            processed_ids_set = set()
        
        # Query for unprocessed chunks
        if start_from_id is not None:
            query = text(f"""
                SELECT id FROM document_chunks 
                WHERE id >= :start_id
                ORDER BY id
                LIMIT :limit
            """)
            result = session.execute(query, {"start_id": start_from_id, "limit": batch_size})
        else:
            query = text("""
                SELECT id FROM document_chunks 
                ORDER BY id
                LIMIT :limit
            """)
            result = session.execute(query, {"limit": batch_size})
        
        # Convert to list and filter out already processed chunks
        all_chunk_ids = [row[0] for row in result]
        unprocessed_ids = [c_id for c_id in all_chunk_ids if c_id not in processed_ids_set]
        
        # If we filtered out all chunks, try getting more
        if not unprocessed_ids and all_chunk_ids and processed_ids_set:
            # Get the highest ID we checked
            last_id = all_chunk_ids[-1]
            
            # Query for more chunks beyond the last one we checked
            query = text("""
                SELECT id FROM document_chunks 
                WHERE id > :last_id
                ORDER BY id
                LIMIT :limit
            """)
            result = session.execute(query, {"last_id": last_id, "limit": batch_size})
            
            # Filter again
            more_chunk_ids = [row[0] for row in result]
            unprocessed_ids = [c_id for c_id in more_chunk_ids if c_id not in processed_ids_set]
        
        session.close()
        return unprocessed_ids[:batch_size]  # Ensure we don't return more than requested
    
    except Exception as e:
        logger.error(f"Error getting next chunk IDs: {e}")
        return []

def process_chunk(chunk_id: int) -> bool:
    """
    Process a single chunk using direct_process_chunk.py
    
    Args:
        chunk_id: ID of the chunk to process
        
    Returns:
        True if processing was successful, False otherwise
    """
    import subprocess
    
    try:
        # Run direct_process_chunk.py for this chunk
        start_time = time.time()
        result = subprocess.run(
            ["python", "direct_process_chunk.py", str(chunk_id)],
            check=True,
            capture_output=True,
            text=True
        )
        
        duration = time.time() - start_time
        logger.info(f"✅ Successfully processed chunk {chunk_id} in {duration:.2f}s")
        
        # Log the output
        for line in result.stdout.splitlines():
            if line.strip():
                logger.debug(f"STDOUT: {line}")
        
        return True
    
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Failed to process chunk {chunk_id}: {e}")
        
        # Log the detailed error output
        if e.stdout:
            for line in e.stdout.splitlines():
                if line.strip():
                    logger.debug(f"STDOUT: {line}")
        
        if e.stderr:
            for line in e.stderr.splitlines():
                if line.strip():
                    logger.error(f"STDERR: {line}")
        
        return False

def process_batch(chunk_ids: List[int]) -> Dict[str, Any]:
    """
    Process a batch of chunks.
    
    Args:
        chunk_ids: List of chunk IDs to process
        
    Returns:
        Dictionary with processing results
    """
    if not chunk_ids:
        return {"successful": 0, "failed": 0, "processed": []}
    
    logger.info(f"Processing batch of {len(chunk_ids)} chunks: {chunk_ids}")
    
    successful = 0
    failed = 0
    processed_chunks = []
    
    for i, chunk_id in enumerate(chunk_ids):
        logger.info(f"Processing chunk {i+1}/{len(chunk_ids)} (ID: {chunk_id})")
        
        # Try processing the chunk with retries
        success = False
        retries = 0
        
        while not success and retries < MAX_RETRIES:
            if retries > 0:
                logger.warning(f"Retry {retries}/{MAX_RETRIES} for chunk {chunk_id}")
                time.sleep(DELAY_BETWEEN_CHUNKS * 2)  # Wait longer between retries
            
            success = process_chunk(chunk_id)
            
            if not success:
                retries += 1
        
        # Record the result
        if success:
            successful += 1
            processed_chunks.append({"id": chunk_id, "success": True})
            
            # Save a checkpoint after each successful chunk
            save_checkpoint(chunk_id, success=True)
        else:
            failed += 1
            processed_chunks.append({"id": chunk_id, "success": False})
            
            # Save a checkpoint for failed chunks too
            save_checkpoint(chunk_id, success=False)
        
        # Pause between chunks to avoid rate limiting
        if i < len(chunk_ids) - 1:  # Don't sleep after the last chunk
            time.sleep(DELAY_BETWEEN_CHUNKS)
    
    logger.info(f"Batch completed. Success: {successful}, Failed: {failed}")
    
    return {
        "successful": successful,
        "failed": failed,
        "processed": processed_chunks
    }

def continuous_processing(max_batches=None, batch_size=DEFAULT_BATCH_SIZE, resume_from_checkpoint=True) -> Dict[str, Any]:
    """
    Continuously process chunks until all are processed or the maximum is reached.
    
    Args:
        max_batches: Maximum number of batches to process (None for unlimited)
        batch_size: Number of chunks to process in each batch
        resume_from_checkpoint: Whether to resume from the last checkpoint
        
    Returns:
        Dictionary with overall processing results
    """
    # Print header
    logger.info("=" * 50)
    logger.info(f"CONTINUOUS PROCESSING: {datetime.now().strftime('%Y%m%d_%H%M%S')}")
    logger.info(f"Batch size: {batch_size}")
    logger.info("=" * 50)
    
    # Start from checkpoint if requested
    start_chunk_id = None
    if resume_from_checkpoint:
        checkpoint = load_checkpoint()
        if checkpoint:
            start_chunk_id = checkpoint.get('chunk_id')
            logger.info(f"Resuming from checkpoint: chunk_id={start_chunk_id}")
    
    # Initialize counters
    batches_processed = 0
    total_successful = 0
    total_failed = 0
    
    # Process until we run out of chunks or reach max_batches
    while max_batches is None or batches_processed < max_batches:
        # Check progress
        try:
            # Try to use check_progress.py if it exists
            logger.info("Checking progress...")
            import subprocess
            
            result = subprocess.run(
                ["python", "check_progress.py"],
                check=True,
                capture_output=True,
                text=True
            )
            
            # Log the output
            for line in result.stdout.splitlines():
                if "VECTOR STORE REBUILD PROGRESS" in line or "Progress:" in line or "Remaining:" in line:
                    logger.info(line.strip())
        except Exception as e:
            logger.warning(f"Could not check progress: {e}")
        
        # Get the next batch of chunks to process
        chunk_ids = get_next_chunk_ids(batch_size, start_chunk_id)
        
        # If we've processed at least one batch, don't use start_chunk_id anymore
        if batches_processed > 0:
            start_chunk_id = None
        
        # If there are no more chunks to process, we're done!
        if not chunk_ids:
            logger.info("No more chunks to process. Exiting.")
            break
        
        # Process this batch
        batch_results = process_batch(chunk_ids)
        
        # Update counters
        total_successful += batch_results["successful"]
        total_failed += batch_results["failed"]
        batches_processed += 1
        
        logger.info(f"Completed batch {batches_processed}")
        logger.info(f"Total successful: {total_successful}, Total failed: {total_failed}")
        
        # Pause between batches to let the system breathe
        if max_batches is None or batches_processed < max_batches:
            logger.info(f"Pausing for {DELAY_BETWEEN_BATCHES} seconds before next batch...")
            time.sleep(DELAY_BETWEEN_BATCHES)
    
    # Print summary
    logger.info("=" * 50)
    logger.info("PROCESSING COMPLETE")
    logger.info(f"Batches processed: {batches_processed}")
    logger.info(f"Total successful: {total_successful}")
    logger.info(f"Total failed: {total_failed}")
    logger.info("=" * 50)
    
    return {
        "batches_processed": batches_processed,
        "total_successful": total_successful,
        "total_failed": total_failed
    }

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Continuous Chunk Processor")
    parser.add_argument(
        "-b", "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Number of chunks to process in each batch (default: {DEFAULT_BATCH_SIZE})"
    )
    parser.add_argument(
        "-m", "--max-batches",
        type=int,
        default=None,
        help="Maximum number of batches to process (default: unlimited)"
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Don't resume from the last checkpoint"
    )
    
    return parser.parse_args()

if __name__ == "__main__":
    # Parse command line arguments
    args = parse_args()
    
    try:
        # Run the continuous processing
        results = continuous_processing(
            max_batches=args.max_batches,
            batch_size=args.batch_size,
            resume_from_checkpoint=not args.no_resume
        )
        
        sys.exit(0 if results["total_failed"] == 0 else 1)
    
    except KeyboardInterrupt:
        logger.info("Processing interrupted by user. Exiting gracefully.")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        sys.exit(1)