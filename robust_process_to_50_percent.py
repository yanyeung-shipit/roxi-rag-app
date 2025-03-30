#!/usr/bin/env python3
"""
Robust Process to 50% Target

This script processes chunks in batches until 50% of all chunks are processed.
It includes enhanced error handling and database connection management.
"""

import os
import sys
import logging
import datetime
import traceback
import time
import shutil
import sqlalchemy.exc

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("robust_process_to_50_percent.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("robust_process_to_50_percent")

# Add the current directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from batch_rebuild_to_target import BatchProcessor
    from app import app, db
except ImportError as e:
    logger.error(f"Failed to import modules: {str(e)}")
    sys.exit(1)

# Constants
TARGET_PERCENTAGE = 50.0
BATCH_SIZE = 5  # Smaller batch size for better reliability
VECTOR_STORE_FILE = "faiss_index.bin"
DOCUMENT_DATA_FILE = "document_data.pkl"
BACKUP_DIR = "backups"
MAX_DB_RETRIES = 3
DB_RETRY_DELAY = 10  # seconds


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


def ensure_db_connection():
    """
    Ensure database connection is valid and retry if needed.
    """
    for attempt in range(MAX_DB_RETRIES):
        try:
            with app.app_context():
                # Try a simple query to check connection
                db.session.execute("SELECT 1").scalar()
                logger.info("Database connection verified")
                return True
        except sqlalchemy.exc.OperationalError as e:
            logger.warning(f"Database connection error (attempt {attempt+1}/{MAX_DB_RETRIES}): {str(e)}")
            try:
                # Try to rollback any pending transactions
                db.session.rollback()
                logger.info("Session rolled back")
            except Exception as rollback_error:
                logger.error(f"Error rolling back session: {str(rollback_error)}")
                
            # Wait before retrying
            if attempt < MAX_DB_RETRIES - 1:
                logger.info(f"Waiting {DB_RETRY_DELAY} seconds before retry...")
                time.sleep(DB_RETRY_DELAY)
        except Exception as e:
            logger.error(f"Unexpected database error: {str(e)}")
            logger.error(traceback.format_exc())
            db.session.rollback()
            if attempt < MAX_DB_RETRIES - 1:
                logger.info(f"Waiting {DB_RETRY_DELAY} seconds before retry...")
                time.sleep(DB_RETRY_DELAY)
    
    logger.error(f"Failed to establish database connection after {MAX_DB_RETRIES} attempts")
    return False


def main():
    """Main function to run the batch processing to 50%."""
    try:
        logger.info(f"Starting processing to {TARGET_PERCENTAGE}% target")
        
        # Verify database connection first
        if not ensure_db_connection():
            logger.error("Cannot proceed without valid database connection")
            return 1
        
        # Create backup
        create_backup()
        
        # Create and run batch processor with reduced batch size for reliability
        processor = BatchProcessor(batch_size=BATCH_SIZE, target_percentage=TARGET_PERCENTAGE)
        
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
    except sqlalchemy.exc.DatabaseError as e:
        logger.error(f"Database error in processing: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Try to recover session
        try:
            db.session.rollback()
            logger.info("Session rolled back")
        except Exception:
            logger.error("Failed to rollback session")
        return 1
    except Exception as e:
        logger.error(f"Error in processing: {str(e)}")
        logger.error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())