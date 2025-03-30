#!/usr/bin/env python3
"""
Process to 50% Target

This script processes chunks in batches until 50% of all chunks are processed.
It creates a backup of the vector store before starting and logs progress.
"""

import os
import sys
import logging
import datetime
import traceback
import time
import shutil
import signal
import atexit

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("process_to_50_percent.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("process_to_50_percent")

# Add the current directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from batch_rebuild_to_target import BatchProcessor
    import models
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker, scoped_session
    from sqlalchemy.pool import QueuePool
except ImportError as e:
    logger.error(f"Failed to import modules: {str(e)}")
    sys.exit(1)

# Constants
TARGET_PERCENTAGE = 50.0
BATCH_SIZE = 10
VECTOR_STORE_FILE = "faiss_index.bin"
DOCUMENT_DATA_FILE = "document_data.pkl"
BACKUP_DIR = "backups"
PID_FILE = "process_50_percent.pid"

# Create a pid file
def create_pid_file():
    """Create a PID file for the current process."""
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

# Remove the pid file on exit
def remove_pid_file():
    """Remove the PID file when the process exits."""
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)

# Setup signal handlers for graceful shutdown
def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown."""
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        remove_pid_file()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(remove_pid_file)


def create_backup():
    """Create a backup of the vector store files."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Backup vector store files
    for file_path in [VECTOR_STORE_FILE, DOCUMENT_DATA_FILE]:
        if os.path.exists(file_path):
            backup_path = os.path.join(BACKUP_DIR, f"{os.path.basename(file_path)}.{timestamp}")
            shutil.copy2(file_path, backup_path)
    
    logger.info("Created vector store backup")
    return True


def main():
    """Main function to run the batch processing to 50%."""
    try:
        # Setup signal handlers and PID file
        setup_signal_handlers()
        create_pid_file()
        
        logger.info(f"Starting processing to {TARGET_PERCENTAGE}% target with PID {os.getpid()}")
        
        # Create backup
        create_backup()
        
        # Create and run batch processor with retry capability
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                processor = BatchProcessor(batch_size=BATCH_SIZE, target_percentage=TARGET_PERCENTAGE)
                
                # Start processing
                start_time = time.time()
                summary = processor.run_until_target()
                end_time = time.time()
                
                # If we got here, processing was successful
                break
            except Exception as e:
                retry_count += 1
                logger.warning(f"Processing attempt {retry_count} failed: {str(e)}")
                
                if retry_count >= max_retries:
                    logger.error("Maximum retry attempts reached")
                    raise
                
                # Wait before retrying (exponential backoff)
                wait_time = 2 ** retry_count
                logger.info(f"Waiting {wait_time} seconds before retrying...")
                time.sleep(wait_time)
        
        # Log final results
        elapsed_time = end_time - start_time
        minutes, seconds = divmod(int(elapsed_time), 60)
        hours, minutes = divmod(minutes, 60)
        
        logger.info(f"Processing completed in {hours}h {minutes}m {seconds}s")
        logger.info(f"Processed {summary['chunks_processed']} chunks in {summary['batches_processed']} batches")
        logger.info(f"Start: {summary['start_percentage']}%, Final: {summary['final_percentage']}%")
        
        return 0
    except Exception as e:
        logger.error(f"Error in processing: {str(e)}")
        logger.error(traceback.format_exc())
        return 1
    finally:
        # Always remove the PID file when exiting
        remove_pid_file()


if __name__ == "__main__":
    sys.exit(main())