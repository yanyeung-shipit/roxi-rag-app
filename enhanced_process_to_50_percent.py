#!/usr/bin/env python3
"""
Enhanced Process to 50% Target

This script uses the enhanced batch processor to process chunks
until 50% of all chunks are processed, with improved error handling
and database connection management.
"""

import os
import sys
import logging
import datetime
import traceback
import time
import shutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("enhanced_process_to_50_percent.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("enhanced_process_to_50_percent")

# Add the current directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from enhanced_batch_processor import EnhancedBatchProcessor
except ImportError as e:
    logger.error(f"Failed to import modules: {str(e)}")
    sys.exit(1)

# Constants
TARGET_PERCENTAGE = 50.0
BATCH_SIZE = 5  # Smaller batch size for better reliability
VECTOR_STORE_FILE = "faiss_index.bin"
DOCUMENT_DATA_FILE = "document_data.pkl"
BACKUP_DIR = "backups"


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
    """Main function to run the enhanced batch processing to 50%."""
    try:
        logger.info(f"Starting enhanced processing to {TARGET_PERCENTAGE}% target")
        
        # Create backup
        create_backup()
        
        # Create and run enhanced batch processor
        processor = EnhancedBatchProcessor(batch_size=BATCH_SIZE, target_percentage=TARGET_PERCENTAGE)
        
        # Start processing
        start_time = time.time()
        summary = processor.run_until_target()
        end_time = time.time()
        
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


if __name__ == "__main__":
    sys.exit(main())