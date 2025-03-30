"""
Run Chunk Processor Script

This script runs the background chunk processor with the specified target percentage.
It's designed to be run regularly to ensure the vector store is continually being updated.

Usage:
    python run_chunk_processor.py --target 75
"""

import argparse
import logging
import os
import subprocess
import sys
import time
from datetime import datetime

# Configure logging
log_file = 'run_chunk_processor.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Constants
DEFAULT_TARGET_PERCENTAGE = 75.0
DEFAULT_BATCH_SIZE = 5
DEFAULT_DELAY_SECONDS = 3
PID_FILE = 'process_chunks_background.pid'

def is_processor_running() -> bool:
    """Check if the background processor is already running."""
    if not os.path.exists(PID_FILE):
        return False
        
    try:
        with open(PID_FILE, 'r') as f:
            pid = int(f.read().strip())
            
        # Check if the process is still running
        os.kill(pid, 0)  # This will raise an exception if the process is not running
        return True
    except (OSError, ValueError):
        # Process is not running or PID file is invalid
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)  # Clean up stale PID file
        return False

def start_processor(target_percentage: float, batch_size: int, delay_seconds: int) -> None:
    """Start the background processor."""
    logger.info(f"Starting background processor with target {target_percentage}%")
    
    cmd = [
        'python', 'process_chunks_background.py',
        '--target', str(target_percentage),
        '--batch-size', str(batch_size),
        '--delay', str(delay_seconds)
    ]
    
    # Start the process in the background
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )
    
    logger.info(f"Started background processor with PID {process.pid}")
    
    # Wait a moment to ensure the process starts correctly
    time.sleep(2)
    
    # Check if the process is still running
    if process.poll() is None:
        logger.info("Background processor started successfully")
    else:
        stdout, _ = process.communicate()
        logger.error(f"Background processor failed to start: {stdout}")

def main():
    """Main function to parse arguments and start the processor."""
    parser = argparse.ArgumentParser(description='Run the background chunk processor')
    parser.add_argument('--target', type=float, default=DEFAULT_TARGET_PERCENTAGE,
                       help=f'Target percentage of completion (default: {DEFAULT_TARGET_PERCENTAGE})')
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE,
                       help=f'Number of chunks to process per batch (default: {DEFAULT_BATCH_SIZE})')
    parser.add_argument('--delay', type=int, default=DEFAULT_DELAY_SECONDS,
                       help=f'Delay between batches in seconds (default: {DEFAULT_DELAY_SECONDS})')
    args = parser.parse_args()
    
    logger.info(f"Checking if background processor is already running")
    
    if is_processor_running():
        logger.info("Background processor is already running")
    else:
        logger.info("Background processor is not running, starting it")
        start_processor(args.target, args.batch_size, args.delay)

if __name__ == '__main__':
    main()