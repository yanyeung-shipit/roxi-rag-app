#!/usr/bin/env python
"""
Vector Store Monitor

This script monitors the vector store for signs of data loss or corruption.
It regularly checks the number of documents and chunks in the vector store
and triggers alerts and recovery actions if problems are detected.
"""

import os
import sys
import time
import pickle
import logging
import subprocess
from datetime import datetime
import signal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("monitor.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("vector_store_monitor")

# Configuration
VECTOR_STORE_PATH = "document_data.pkl"
INDEX_PATH = "faiss_index.bin"
CHECK_INTERVAL = 300  # 5 minutes
THRESHOLD_PERCENTAGE = 10  # Alert if more than 10% of data is lost
BACKUP_SCRIPT = "backup_vector_store.py"

# Global variables to track state
last_known_count = None
consecutive_errors = 0
monitor_start_time = datetime.now()

def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    logger.info("Monitor shutting down...")
    sys.exit(0)

def get_vector_store_counts():
    """
    Get the number of documents and chunks in the vector store.
    
    Returns:
        tuple: (document_count, chunk_count, status)
    """
    if not os.path.exists(VECTOR_STORE_PATH):
        logger.error(f"Vector store file not found: {VECTOR_STORE_PATH}")
        return 0, 0, "missing"
    
    if not os.path.exists(INDEX_PATH):
        logger.error(f"Index file not found: {INDEX_PATH}")
        return 0, 0, "missing"
    
    try:
        # Load the vector store
        with open(VECTOR_STORE_PATH, 'rb') as f:
            data = pickle.load(f)
        
        # Count documents and chunks
        if not isinstance(data, dict):
            logger.error(f"Vector store data is not a dictionary")
            return 0, 0, "corrupt"
        
        if 'documents' not in data:
            logger.error(f"Vector store missing 'documents' key")
            return 0, 0, "corrupt"
            
        documents = data.get('documents', {})
        chunks = 0
        
        # Count chunks across all documents
        for doc_id, doc in documents.items():
            if 'chunks' in doc:
                chunks += len(doc['chunks'])
        
        return len(documents), chunks, "ok"
    except Exception as e:
        logger.error(f"Error reading vector store: {e}")
        return 0, 0, "error"

def trigger_backup():
    """Trigger an immediate backup."""
    logger.info("Triggering immediate backup...")
    try:
        subprocess.run(["python", BACKUP_SCRIPT], check=True)
        logger.info("Backup completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Backup failed: {e}")
        return False

def check_vector_store():
    """
    Check the vector store for signs of data loss.
    
    Returns:
        bool: True if everything is OK, False if problems were detected
    """
    global last_known_count, consecutive_errors
    
    try:
        # Get current counts
        doc_count, chunk_count, status = get_vector_store_counts()
        
        # Format for logging
        logger.info(f"Vector store status: {status}")
        logger.info(f"Documents: {doc_count}, Chunks: {chunk_count}")
        
        # If this is the first check, just store the counts
        if last_known_count is None:
            last_known_count = (doc_count, chunk_count)
            logger.info(f"Initial state recorded: {doc_count} documents, {chunk_count} chunks")
            return True
            
        # Check for significant data loss
        last_docs, last_chunks = last_known_count
        
        # Calculate percentage change if previous values were non-zero
        doc_change_pct = 0
        chunk_change_pct = 0
        
        if last_docs > 0:
            doc_change_pct = 100 * (last_docs - doc_count) / last_docs
            
        if last_chunks > 0:
            chunk_change_pct = 100 * (last_chunks - chunk_count) / last_chunks
        
        # Log changes
        logger.info(f"Change since last check: Documents: {doc_change_pct:.1f}%, Chunks: {chunk_change_pct:.1f}%")
        
        # Check for problems
        if status != "ok":
            logger.error(f"Vector store is in an unhealthy state: {status}")
            consecutive_errors += 1
            return False
            
        if doc_count < last_docs and doc_change_pct > THRESHOLD_PERCENTAGE:
            logger.warning(f"Document count decreased by {doc_change_pct:.1f}% - possible data loss!")
            consecutive_errors += 1
            return False
            
        if chunk_count < last_chunks and chunk_change_pct > THRESHOLD_PERCENTAGE:
            logger.warning(f"Chunk count decreased by {chunk_change_pct:.1f}% - possible data loss!")
            consecutive_errors += 1
            return False
        
        # Update last known count if everything is OK
        last_known_count = (doc_count, chunk_count)
        consecutive_errors = 0
        return True
        
    except Exception as e:
        logger.error(f"Error during vector store check: {e}")
        consecutive_errors += 1
        return False

def main():
    """Main monitoring loop."""
    global consecutive_errors
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("Vector store monitor started")
    
    try:
        while True:
            logger.info(f"Performing vector store check...")
            status_ok = check_vector_store()
            
            # Take action based on status
            if not status_ok:
                logger.warning(f"Vector store check failed (consecutive errors: {consecutive_errors})")
                
                if consecutive_errors >= 3:
                    logger.error(f"Multiple consecutive errors detected - triggering recovery")
                    trigger_backup()
                    
                    # Reset error counter after attempted recovery
                    consecutive_errors = 0
            else:
                logger.info("Vector store check passed")
            
            # Calculate runtime
            runtime = datetime.now() - monitor_start_time
            logger.info(f"Monitor has been running for {runtime}")
            
            # Wait for next check
            logger.info(f"Next check in {CHECK_INTERVAL} seconds")
            time.sleep(CHECK_INTERVAL)
            
    except Exception as e:
        logger.error(f"Unhandled exception in monitor: {e}")
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())