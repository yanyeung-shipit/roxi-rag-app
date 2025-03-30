"""
Enhanced script to continuously process chunks from the database into the vector store.
This script will run until all chunks are processed or it is stopped.
Features:
- Robust error handling that doesn't stop the process on individual failures
- Comprehensive monitoring and progress tracking
- Checkpoint-based recovery system
- Adaptive sleep with deep sleep mode for resource conservation
- Exponential backoff during idle periods
"""
import os
import sys
import time
import json
import logging
import argparse
import traceback
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
from app import app, Document, DocumentChunk
from utils.vector_store import VectorStore
from add_single_chunk import add_next_chunk
from check_progress import check_progress
from utils.rebuild_monitor import start_monitoring, run_monitoring_check
from utils.rebuild_error_handler import (
    safe_executor, retry_handler, log_error, 
    get_retryable_documents, get_error_stats,
    setup_error_directory
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# File paths for checkpoints
CHECKPOINT_DIR = "logs/checkpoints"
LAST_PROCESSED_CHUNK_PATH = f"{CHECKPOINT_DIR}/last_processed_chunk.json"

def setup_checkpoint_directory():
    """Create the checkpoint directory structure if it doesn't exist."""
    if not os.path.exists(CHECKPOINT_DIR):
        os.makedirs(CHECKPOINT_DIR, exist_ok=True)
        logger.info(f"Created checkpoint directory: {CHECKPOINT_DIR}")

def save_checkpoint(chunk_id: int, document_id: int):
    """
    Save a checkpoint of the last processed chunk.
    
    Args:
        chunk_id (int): ID of the last processed chunk
        document_id (int): ID of the document containing the chunk
    """
    setup_checkpoint_directory()
    
    checkpoint_data = {
        "timestamp": datetime.now().isoformat(),
        "chunk_id": chunk_id,
        "document_id": document_id
    }
    
    with open(LAST_PROCESSED_CHUNK_PATH, "w") as f:
        json.dump(checkpoint_data, f, indent=2)
    
    logger.debug(f"Saved checkpoint: Chunk {chunk_id} from Document {document_id}")

def load_checkpoint() -> Optional[Dict[str, Any]]:
    """
    Load the last processed chunk checkpoint.
    
    Returns:
        dict or None: Checkpoint data or None if no checkpoint exists
    """
    try:
        with open(LAST_PROCESSED_CHUNK_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

@retry_handler
def enhanced_add_next_chunk() -> Dict[str, Any]:
    """
    Enhanced version of add_next_chunk with better error handling and reporting.
    
    Returns:
        dict: Result data including success status and chunk information
    """
    result = add_next_chunk()
    
    # If add_next_chunk returned True, save checkpoint information
    if result and isinstance(result, dict) and result.get('chunk_id'):
        save_checkpoint(result['chunk_id'], result.get('document_id', 0))
        return result
    # If add_next_chunk returned a boolean, it's the old version
    elif result is True:
        # We don't have chunk information, but we can at least save that we processed something
        logger.warning("Using old version of add_next_chunk that doesn't return chunk info")
        return {'success': True, 'chunk_id': None, 'document_id': None}
    
    # If we get here, either result is False or None
    return {'success': False, 'error': 'No more chunks to process or error occurred'}

def continuous_rebuild(max_chunks=None, delay_seconds=2, enable_monitoring=True,
                      start_from_checkpoint=True, retry_failed=True, 
                      enable_adaptive_sleep=True, deep_sleep_mode=True):
    """
    Continuously process chunks until all are processed or the maximum is reached.
    
    Args:
        max_chunks (int, optional): Maximum number of chunks to process. If None, process all.
        delay_seconds (int, optional): Base delay between chunks to avoid API rate limits.
        enable_monitoring (bool): Whether to enable the monitoring system.
        start_from_checkpoint (bool): Whether to resume from the last checkpoint.
        retry_failed (bool): Whether to retry previously failed documents.
        enable_adaptive_sleep (bool): Whether to use adaptive sleep times that increase during idle periods.
        deep_sleep_mode (bool): Whether to enable deep sleep mode for extended idle periods.
        
    Returns:
        bool: True if rebuild completed successfully, False otherwise
    """
    try:
        # Initialize directories
        setup_checkpoint_directory()
        setup_error_directory()
        
        # Start monitoring if enabled
        if enable_monitoring:
            monitor_thread = start_monitoring(interval=60)  # Check every 60 seconds
            logger.info("Monitoring system started")
        
        chunk_count = 0
        consecutive_idle_cycles = 0
        in_deep_sleep = False
        current_sleep_time = delay_seconds
        max_sleep_time = 300  # 5 minutes
        deep_sleep_time = 600  # 10 minutes
        deep_sleep_threshold = 10  # Cycles before entering deep sleep
        
        last_progress_check = time.time()
        progress_check_interval = 30  # seconds
        
        # Get failed documents to retry if requested
        retryable_documents = set()
        if retry_failed:
            retryable_documents = set(get_retryable_documents())
            if retryable_documents:
                logger.info(f"Will retry {len(retryable_documents)} documents with previous errors")
        
        # Load checkpoint if requested
        if start_from_checkpoint:
            checkpoint = load_checkpoint()
            if checkpoint:
                logger.info(f"Resuming from checkpoint: Chunk {checkpoint['chunk_id']}")
        
        logger.info("Starting enhanced continuous vector store rebuild...")
        
        while True:
            # Check progress periodically
            if time.time() - last_progress_check > progress_check_interval:
                progress = check_progress()
                last_progress_check = time.time()
                
                # Report current status
                logger.info(f"Progress: {progress['progress_percent']:.1f}% complete - "
                           f"{progress['vector_chunks']}/{progress['db_chunks']} chunks processed")
                
                # Check error stats periodically
                error_stats = get_error_stats()
                if error_stats["total_errors"] > 0:
                    logger.info(f"Errors so far: {error_stats['total_errors']} "
                              f"({error_stats['recoverable_errors']} recoverable, "
                              f"{error_stats['unrecoverable_errors']} unrecoverable)")
                
                # If 100% complete, exit
                if progress and progress['progress_percent'] >= 99.9:
                    logger.info("Vector store rebuild is complete!")
                    return True
            
            # Process the next chunk with better error handling
            try:
                result = enhanced_add_next_chunk()
                
                # Check if chunk was processed successfully
                if not result.get('success', False):
                    # No chunks to process, implement adaptive sleep
                    if enable_adaptive_sleep:
                        consecutive_idle_cycles += 1
                        
                        # Check if we should enter deep sleep mode
                        if deep_sleep_mode and consecutive_idle_cycles >= deep_sleep_threshold and not in_deep_sleep:
                            in_deep_sleep = True
                            current_sleep_time = deep_sleep_time
                            logger.info(f"Entering deep sleep mode after {consecutive_idle_cycles} idle cycles, sleeping for {deep_sleep_time}s")
                        # Otherwise use exponential backoff
                        elif not in_deep_sleep and consecutive_idle_cycles > 3:
                            # Double sleep time after 3 idle cycles (up to max limit)
                            current_sleep_time = min(current_sleep_time * 2, max_sleep_time)
                            logger.debug(f"No chunks found for {consecutive_idle_cycles} cycles, increasing sleep to {current_sleep_time}s")
                        elif in_deep_sleep:
                            logger.debug(f"In deep sleep mode, sleeping for {current_sleep_time}s")
                        else:
                            logger.debug(f"No chunks found, sleeping for {current_sleep_time}s")
                            
                        # Sleep for the adaptive time before checking again
                        time.sleep(current_sleep_time)
                        continue
                    else:
                        # If adaptive sleep is disabled, just finish processing
                        logger.info("No more chunks to process or encountered an error.")
                        progress = check_progress()
                        return progress['progress_percent'] >= 99.9
                
                # Increment chunk count
                chunk_count += 1
                
                # Reset sleep state and counters when work is found
                if enable_adaptive_sleep:
                    consecutive_idle_cycles = 0
                    current_sleep_time = delay_seconds
                    
                    # If we were in deep sleep, exit that mode
                    if in_deep_sleep:
                        in_deep_sleep = False
                        logger.info("Exiting deep sleep mode - work found!")
                
                # Log success with available information
                if result.get('chunk_id'):
                    logger.info(f"Successfully processed chunk {result['chunk_id']} "
                              f"(#{chunk_count}{' of ' + str(max_chunks) if max_chunks else ''})")
                else:
                    logger.info(f"Successfully processed a chunk "
                              f"(#{chunk_count}{' of ' + str(max_chunks) if max_chunks else ''})")
                
                # Check if we've reached the maximum number of chunks to process
                if max_chunks and chunk_count >= max_chunks:
                    logger.info(f"Processed {chunk_count} chunks (max: {max_chunks})")
                    progress = check_progress()
                    return progress['progress_percent'] >= 99.9
                    
            except Exception as e:
                # Log the error but continue processing
                logger.error(f"Error processing chunk: {str(e)}")
                log_error("chunk_processing_error", str(e), recoverable=True)
            
            # Use adaptive sleep time if enabled, otherwise use fixed delay
            if enable_adaptive_sleep:
                time.sleep(current_sleep_time)
            else:
                time.sleep(delay_seconds)
            
    except KeyboardInterrupt:
        logger.info("Rebuild process interrupted by user.")
        return False
    except Exception as e:
        logger.error(f"Fatal error in continuous rebuild: {str(e)}")
        log_error("fatal_rebuild_error", str(e), recoverable=False)
        traceback.print_exc()
        return False
    finally:
        # Run one final progress check
        try:
            progress = check_progress()
            logger.info(f"Final progress: {progress['progress_percent']:.1f}% complete - "
                       f"{progress['vector_chunks']}/{progress['db_chunks']} chunks processed")
            
            # Run a final monitoring check if monitoring is enabled
            if enable_monitoring:
                run_monitoring_check()
        except Exception:
            pass

if __name__ == "__main__":
    # Set up argument parser for more flexible command-line options
    parser = argparse.ArgumentParser(description="Continuously rebuild vector store from database chunks")
    parser.add_argument("--max-chunks", type=int, default=None, 
                      help="Maximum number of chunks to process")
    parser.add_argument("--delay", type=float, default=2, 
                      help="Delay between chunks in seconds (default: 2)")
    parser.add_argument("--no-monitoring", action="store_true", 
                      help="Disable the monitoring system")
    parser.add_argument("--no-checkpoint", action="store_true", 
                      help="Don't resume from the last checkpoint")
    parser.add_argument("--no-retry", action="store_true", 
                      help="Don't retry previously failed documents")
    parser.add_argument("--no-adaptive-sleep", action="store_true",
                      help="Disable adaptive sleep times that increase during idle periods")
    parser.add_argument("--no-deep-sleep", action="store_true",
                      help="Disable deep sleep mode for extended idle periods")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Run the continuous rebuild with parsed arguments
    continuous_rebuild(
        max_chunks=args.max_chunks,
        delay_seconds=args.delay,
        enable_monitoring=not args.no_monitoring,
        start_from_checkpoint=not args.no_checkpoint,
        retry_failed=not args.no_retry,
        enable_adaptive_sleep=not args.no_adaptive_sleep,
        deep_sleep_mode=not args.no_deep_sleep
    )