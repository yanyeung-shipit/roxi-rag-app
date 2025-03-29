"""
Comprehensive monitoring system for the vector store rebuild process.
This module provides tools to track progress, identify bottlenecks, and log performance metrics.
"""
import os
import json
import time
import logging
import threading
from datetime import datetime, timedelta
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, scoped_session
from models import Document, DocumentChunk

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize database connection
DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL)
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)

# Monitoring state
MONITORING_STATE = {
    "is_running": False,
    "start_time": None,
    "last_check_time": None,
    "total_checks": 0,
    "total_chunks_processed": 0,
    "previous_chunks_processed": 0,
    "processing_rates": [],
    "bottlenecks": [],
    "errors": []
}

# File paths for logs
MONITOR_LOG_DIR = "logs/monitoring"
ERROR_LOG_PATH = f"{MONITOR_LOG_DIR}/rebuild_errors.log"
PERFORMANCE_LOG_PATH = f"{MONITOR_LOG_DIR}/rebuild_performance.json"
STATUS_LOG_PATH = f"{MONITOR_LOG_DIR}/rebuild_status.json"

def setup_monitoring_directory():
    """Create the monitoring directory structure if it doesn't exist."""
    if not os.path.exists(MONITOR_LOG_DIR):
        os.makedirs(MONITOR_LOG_DIR, exist_ok=True)
        logger.info(f"Created monitoring directory: {MONITOR_LOG_DIR}")

def log_error(error_type, message, document_id=None, details=None):
    """
    Log an error to the error log file.
    
    Args:
        error_type (str): Type of error
        message (str): Error message
        document_id (int, optional): ID of the document related to the error
        details (dict, optional): Additional error details
    """
    setup_monitoring_directory()
    
    error_entry = {
        "timestamp": datetime.now().isoformat(),
        "error_type": error_type,
        "message": message,
        "document_id": document_id,
        "details": details or {}
    }
    
    # Update the monitoring state
    MONITORING_STATE["errors"].append(error_entry)
    
    # Write to the error log file
    with open(ERROR_LOG_PATH, "a") as f:
        f.write(json.dumps(error_entry) + "\n")
    
    # Log to the console
    logger.error(f"REBUILD ERROR: {error_type} - {message}")

def get_database_stats():
    """
    Get current statistics from the database.
    
    Returns:
        dict: Database statistics
    """
    session = Session()
    try:
        # Get document counts
        total_docs = session.query(func.count(Document.id)).scalar() or 0
        processed_docs = session.query(func.count(Document.id)).filter(Document.processed == True).scalar() or 0
        unprocessed_docs = session.query(func.count(Document.id)).filter(Document.processed == False).scalar() or 0
        
        # Get chunk counts
        total_chunks = session.query(func.count(DocumentChunk.id)).scalar() or 0
        
        # Get chunks per document
        chunks_per_doc = []
        if total_docs > 0:
            chunk_counts = session.query(
                DocumentChunk.document_id, 
                func.count(DocumentChunk.id).label('chunk_count')
            ).group_by(DocumentChunk.document_id).all()
            
            chunks_per_doc = [{"document_id": doc_id, "chunk_count": count} for doc_id, count in chunk_counts]
        
        # Get recently processed docs
        recent_docs = session.query(Document).order_by(Document.updated_at.desc()).limit(5).all()
        recent_doc_info = [
            {
                "id": doc.id,
                "filename": doc.filename,
                "processed": doc.processed,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                "chunk_count": len(doc.chunks)
            }
            for doc in recent_docs
        ]
        
        return {
            "total_docs": total_docs,
            "processed_docs": processed_docs,
            "unprocessed_docs": unprocessed_docs,
            "total_chunks": total_chunks,
            "chunks_per_doc": chunks_per_doc,
            "recent_docs": recent_doc_info
        }
    
    except Exception as e:
        logger.error(f"Error getting database stats: {str(e)}")
        return {
            "error": str(e)
        }
    finally:
        session.close()

def get_vector_store_stats():
    """
    Get current statistics from the vector store.
    
    Returns:
        dict: Vector store statistics
    """
    try:
        from utils.vector_store import VectorStore
        vector_store = VectorStore()
        stats = vector_store.get_stats()
        
        return stats
    except Exception as e:
        logger.error(f"Error getting vector store stats: {str(e)}")
        return {
            "error": str(e)
        }

def calculate_progress_stats(db_stats, vector_stats):
    """
    Calculate progress statistics based on database and vector store stats.
    
    Args:
        db_stats (dict): Database statistics
        vector_stats (dict): Vector store statistics
        
    Returns:
        dict: Progress statistics
    """
    vector_chunks = vector_stats.get('total_documents', 0)
    db_chunks = db_stats.get('total_chunks', 0)
    
    # Calculate progress percentage
    progress_percent = (vector_chunks / db_chunks * 100) if db_chunks > 0 else 0
    
    # Calculate chunks remaining
    chunks_remaining = max(0, db_chunks - vector_chunks)
    
    # Calculate estimated time based on processing rate
    processing_rate = 0
    estimated_seconds = 0
    estimated_completion = None
    
    if MONITORING_STATE["total_checks"] > 1:
        time_elapsed = (datetime.now() - MONITORING_STATE["last_check_time"]).total_seconds()
        chunks_processed = vector_chunks - MONITORING_STATE["previous_chunks_processed"]
        
        if time_elapsed > 0:
            processing_rate = chunks_processed / time_elapsed  # chunks per second
            
            if processing_rate > 0:
                estimated_seconds = chunks_remaining / processing_rate
                estimated_completion = datetime.now() + timedelta(seconds=estimated_seconds)
                
                # Store the processing rate for trend analysis
                MONITORING_STATE["processing_rates"].append({
                    "timestamp": datetime.now().isoformat(),
                    "rate": processing_rate,
                    "chunks_processed": chunks_processed,
                    "time_elapsed": time_elapsed
                })
    
    # Update monitoring state
    MONITORING_STATE["previous_chunks_processed"] = vector_chunks
    MONITORING_STATE["last_check_time"] = datetime.now()
    MONITORING_STATE["total_checks"] += 1
    
    # Calculate totals
    return {
        "progress_percent": progress_percent,
        "vector_chunks": vector_chunks,
        "db_chunks": db_chunks,
        "chunks_remaining": chunks_remaining,
        "processing_rate": processing_rate,  # chunks per second
        "estimated_seconds_remaining": estimated_seconds,
        "estimated_completion_time": estimated_completion.isoformat() if estimated_completion else None
    }

def check_bottlenecks(db_stats, vector_stats, progress_stats):
    """
    Check for bottlenecks in the rebuild process.
    
    Args:
        db_stats (dict): Database statistics
        vector_stats (dict): Vector store statistics
        progress_stats (dict): Progress statistics
        
    Returns:
        list: Detected bottlenecks
    """
    bottlenecks = []
    
    # Check if processing rate is too low (less than 0.1 chunks per second)
    if progress_stats.get("processing_rate", 0) < 0.1 and MONITORING_STATE["total_checks"] > 3:
        bottlenecks.append({
            "type": "low_processing_rate",
            "details": f"Processing rate is low: {progress_stats.get('processing_rate', 0):.3f} chunks/second"
        })
    
    # Check if no progress has been made since last check
    if progress_stats.get("vector_chunks", 0) == MONITORING_STATE["previous_chunks_processed"] and MONITORING_STATE["total_checks"] > 1:
        bottlenecks.append({
            "type": "no_progress",
            "details": "No new chunks have been processed since the last check"
        })
    
    # Check if error rate is high (more than 5 errors)
    if len(MONITORING_STATE["errors"]) > 5:
        bottlenecks.append({
            "type": "high_error_rate",
            "details": f"High error rate: {len(MONITORING_STATE['errors'])} errors logged"
        })
    
    return bottlenecks

def save_monitoring_results(db_stats, vector_stats, progress_stats, bottlenecks):
    """
    Save monitoring results to log files.
    
    Args:
        db_stats (dict): Database statistics
        vector_stats (dict): Vector store statistics
        progress_stats (dict): Progress statistics
        bottlenecks (list): Detected bottlenecks
    """
    setup_monitoring_directory()
    
    # Create the status report
    status_report = {
        "timestamp": datetime.now().isoformat(),
        "db_stats": db_stats,
        "vector_stats": vector_stats,
        "progress": progress_stats,
        "bottlenecks": bottlenecks,
        "errors_count": len(MONITORING_STATE["errors"]),
        "monitoring_info": {
            "total_checks": MONITORING_STATE["total_checks"],
            "start_time": MONITORING_STATE["start_time"].isoformat() if MONITORING_STATE["start_time"] else None,
            "running_time": (datetime.now() - MONITORING_STATE["start_time"]).total_seconds() if MONITORING_STATE["start_time"] else 0
        }
    }
    
    # Save to status log file (overwrite)
    with open(STATUS_LOG_PATH, "w") as f:
        json.dump(status_report, f, indent=2)
    
    # Save to performance log file (append latest data)
    performance_data = {
        "timestamp": datetime.now().isoformat(),
        "vector_chunks": progress_stats.get("vector_chunks", 0),
        "progress_percent": progress_stats.get("progress_percent", 0),
        "processing_rate": progress_stats.get("processing_rate", 0),
        "bottlenecks": [b["type"] for b in bottlenecks]
    }
    
    with open(PERFORMANCE_LOG_PATH, "a") as f:
        f.write(json.dumps(performance_data) + "\n")
    
    # Update MONITORING_STATE with bottlenecks
    MONITORING_STATE["bottlenecks"] = bottlenecks

def print_monitoring_report(db_stats, vector_stats, progress_stats, bottlenecks):
    """
    Print a monitoring report to the console.
    
    Args:
        db_stats (dict): Database statistics
        vector_stats (dict): Vector store statistics
        progress_stats (dict): Progress statistics
        bottlenecks (list): Detected bottlenecks
    """
    logger.info("=" * 50)
    logger.info("VECTOR STORE REBUILD MONITORING REPORT")
    logger.info("=" * 50)
    
    # Progress information
    logger.info(f"Progress: {progress_stats.get('progress_percent', 0):.1f}% complete")
    logger.info(f"Chunks: {progress_stats.get('vector_chunks', 0)}/{progress_stats.get('db_chunks', 0)}")
    logger.info(f"Remaining: {progress_stats.get('chunks_remaining', 0)} chunks")
    
    # Processing rate
    if progress_stats.get("processing_rate", 0) > 0:
        rate = progress_stats.get("processing_rate", 0)
        logger.info(f"Processing rate: {rate:.3f} chunks/second ({rate * 60:.1f} chunks/minute)")
    
    # Estimated completion
    if progress_stats.get("estimated_completion_time"):
        logger.info(f"Estimated completion: {progress_stats.get('estimated_completion_time')}")
        
        # Calculate remaining time in a human-readable format
        seconds = progress_stats.get("estimated_seconds_remaining", 0)
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        
        logger.info(f"Estimated time remaining: {hours}h {minutes}m")
    
    # Bottlenecks
    if bottlenecks:
        logger.info("-" * 50)
        logger.info("BOTTLENECKS DETECTED:")
        for bottleneck in bottlenecks:
            logger.info(f"- {bottleneck['type']}: {bottleneck['details']}")
    
    # Error count
    if MONITORING_STATE["errors"]:
        logger.info("-" * 50)
        logger.info(f"ERRORS: {len(MONITORING_STATE['errors'])} errors logged")
        
        # Show the 3 most recent errors
        recent_errors = MONITORING_STATE["errors"][-3:]
        for error in recent_errors:
            logger.info(f"- {error['error_type']}: {error['message']}")
    
    logger.info("=" * 50)

def run_monitoring_check():
    """
    Run a single monitoring check and update logs.
    
    Returns:
        dict: Status report
    """
    # Get stats
    db_stats = get_database_stats()
    vector_stats = get_vector_store_stats()
    
    # Calculate progress
    progress_stats = calculate_progress_stats(db_stats, vector_stats)
    
    # Check for bottlenecks
    bottlenecks = check_bottlenecks(db_stats, vector_stats, progress_stats)
    
    # Save monitoring results
    save_monitoring_results(db_stats, vector_stats, progress_stats, bottlenecks)
    
    # Print report
    print_monitoring_report(db_stats, vector_stats, progress_stats, bottlenecks)
    
    return {
        "db_stats": db_stats,
        "vector_stats": vector_stats,
        "progress": progress_stats,
        "bottlenecks": bottlenecks
    }

def monitoring_loop(interval=60):
    """
    Main monitoring loop that runs checks at regular intervals.
    
    Args:
        interval (int): Time between checks in seconds
    """
    MONITORING_STATE["is_running"] = True
    MONITORING_STATE["start_time"] = datetime.now()
    MONITORING_STATE["last_check_time"] = datetime.now()
    
    logger.info(f"Starting monitoring loop with interval of {interval} seconds")
    
    try:
        while MONITORING_STATE["is_running"]:
            try:
                run_monitoring_check()
                
                # Check if the rebuild is complete
                db_stats = get_database_stats()
                vector_stats = get_vector_store_stats()
                
                db_chunks = db_stats.get('total_chunks', 0)
                vector_chunks = vector_stats.get('total_documents', 0)
                
                if vector_chunks >= db_chunks and db_chunks > 0:
                    logger.info("REBUILD COMPLETE! All chunks have been processed.")
                    break
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {str(e)}")
                log_error("monitoring_error", str(e))
            
            # Sleep until next check
            time.sleep(interval)
    
    except KeyboardInterrupt:
        logger.info("Monitoring loop stopped by user")
    
    finally:
        MONITORING_STATE["is_running"] = False
        logger.info("Monitoring loop ended")

def start_monitoring(interval=60):
    """
    Start the monitoring system in a separate thread.
    
    Args:
        interval (int): Time between checks in seconds
        
    Returns:
        threading.Thread: The monitoring thread
    """
    if MONITORING_STATE["is_running"]:
        logger.info("Monitoring is already running")
        return None
    
    # Create the monitoring directory
    setup_monitoring_directory()
    
    # Start the monitoring loop in a separate thread
    monitor_thread = threading.Thread(target=monitoring_loop, args=(interval,))
    monitor_thread.daemon = True
    monitor_thread.start()
    
    logger.info(f"Monitoring started with interval of {interval} seconds")
    return monitor_thread

def stop_monitoring():
    """
    Stop the monitoring system.
    """
    MONITORING_STATE["is_running"] = False
    logger.info("Monitoring stopped")

if __name__ == "__main__":
    # When run directly, perform a single monitoring check
    run_monitoring_check()