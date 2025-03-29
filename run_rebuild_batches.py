"""
Script to run rebuild batches continuously in the foreground.
This avoids background process issues on the Replit platform.

This enhanced version runs until all chunks are processed or it's manually interrupted.
It uses smaller batch sizes to avoid timeouts and reports progress regularly.
"""
import subprocess
import time
import sys
import logging
import json
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('rebuild_batches.log')
    ]
)

# Default settings
DEFAULT_BATCH_SIZE = 3  # Process fewer chunks per batch to avoid timeouts
DEFAULT_BATCH_DELAY = 2  # Delay between batches in seconds
DEFAULT_MAX_BATCHES = None  # Run indefinitely until all chunks are processed

def run_batch(batch_size):
    """
    Run a single batch of chunk processing.
    
    Args:
        batch_size (int): Number of chunks to process in this batch
        
    Returns:
        bool: True if batch completed successfully, False otherwise
    """
    try:
        logging.info(f"Starting batch with {batch_size} chunks")
        result = subprocess.run(
            ["python3", "add_single_chunk.py", "--max-chunks", str(batch_size)],
            check=True,
            capture_output=True,
            text=True
        )
        logging.info(f"Batch completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Batch failed with error: {e}")
        logging.error(f"STDOUT: {e.stdout}")
        logging.error(f"STDERR: {e.stderr}")
        return False

def check_progress():
    """
    Check the current progress of the rebuild.
    
    Returns:
        dict: Progress information or None if check failed
    """
    try:
        # Run check_progress.py with JSON output
        result = subprocess.run(
            ["python3", "check_progress.py", "--json"],
            check=True,
            capture_output=True,
            text=True
        )
        
        # Parse the JSON output
        output_lines = result.stdout.strip().split('\n')
        for line in output_lines:
            if line.startswith('{') and line.endswith('}'):
                return json.loads(line)
        
        return None
    except Exception as e:
        logging.error(f"Failed to check progress: {e}")
        return None

def is_processing_complete():
    """
    Check if all chunks have been processed.
    
    Returns:
        bool: True if all chunks are processed, False otherwise
    """
    progress_info = check_progress()
    if not progress_info:
        return False
    
    # Check if all chunks are processed
    return progress_info.get('vector_count', 0) >= progress_info.get('db_count', 0)

def main():
    """Run batches until all chunks are processed or max batches is reached."""
    parser = argparse.ArgumentParser(description="Run rebuild batches continuously")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, 
                        help=f"Number of chunks to process in each batch (default: {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--batch-delay", type=int, default=DEFAULT_BATCH_DELAY,
                        help=f"Delay between batches in seconds (default: {DEFAULT_BATCH_DELAY})")
    parser.add_argument("--max-batches", type=int, default=DEFAULT_MAX_BATCHES,
                        help="Maximum number of batches to process (default: unlimited)")
    
    args = parser.parse_args()
    
    batch_count = 0
    success_count = 0
    
    logging.info(f"Starting rebuild process with batch size: {args.batch_size}, delay: {args.batch_delay}s")
    
    try:
        while True:
            # Check if we've reached the maximum number of batches
            if args.max_batches is not None and batch_count >= args.max_batches:
                logging.info(f"Reached maximum batch count ({args.max_batches}), stopping")
                break
            
            # Check if all chunks have been processed
            if is_processing_complete():
                logging.info("All chunks have been processed, stopping")
                break
            
            batch_count += 1
            logging.info(f"Starting batch {batch_count}")
            
            # Run the batch
            if run_batch(args.batch_size):
                success_count += 1
            
            # Check progress after each batch
            progress_info = check_progress()
            if progress_info:
                completed_pct = progress_info.get('progress_pct', 0)
                remaining = progress_info.get('remaining', 0)
                logging.info(f"Progress: {completed_pct:.1f}% complete, {remaining} chunks remaining")
            
            # Sleep before the next batch
            logging.info(f"Sleeping for {args.batch_delay} seconds")
            time.sleep(args.batch_delay)
            
    except KeyboardInterrupt:
        logging.info("Process interrupted by user")
    
    # Final summary
    logging.info(f"Rebuild process completed. Batches run: {batch_count}, successful: {success_count}")
    
    # Final progress check
    progress_info = check_progress()
    if progress_info:
        logging.info(f"Final progress: {progress_info.get('progress_pct', 0):.1f}% complete")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Process interrupted by user")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Unhandled exception: {e}")
        logging.error(f"Stack trace:", exc_info=True)
        sys.exit(1)