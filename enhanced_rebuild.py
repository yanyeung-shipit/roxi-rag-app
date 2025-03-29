#!/usr/bin/env python3
"""
Enhanced rebuild script that combines monitoring and improved error handling.
This script is designed to be run in the background to rebuild the vector store.
"""
import os
import sys
import time
import argparse
import logging
import signal
import traceback
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import monitoring and error handling utilities
try:
    from utils.rebuild_monitor import start_monitoring, run_monitoring_check, stop_monitoring
    from utils.rebuild_error_handler import safe_executor, get_error_stats, get_retryable_documents
    from continuous_rebuild import continuous_rebuild
    from check_progress import check_progress
except ImportError as e:
    logger.error(f"Failed to import required modules: {e}")
    sys.exit(1)

# Create a PID file to prevent multiple instances from running
PID_FILE = "rebuild_process.pid"

def write_pid_file():
    """Write the current process ID to the PID file."""
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    logger.info(f"PID file created: {PID_FILE}")

def remove_pid_file():
    """Remove the PID file."""
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
        logger.info(f"PID file removed: {PID_FILE}")

def is_rebuild_running():
    """Check if a rebuild process is already running."""
    if not os.path.exists(PID_FILE):
        return False
    
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        
        # Check if the process is still running
        os.kill(pid, 0)  # This will raise an exception if the process is not running
        return True
    except (ProcessLookupError, ValueError, OSError):
        # Process not running, clean up the stale PID file
        remove_pid_file()
        return False

def signal_handler(sig, frame):
    """Handle SIGINT and SIGTERM signals to clean up resources."""
    logger.info("Received signal to terminate, cleaning up...")
    stop_monitoring()
    remove_pid_file()
    sys.exit(0)

def setup_signal_handlers():
    """Set up signal handlers for graceful shutdown."""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

@safe_executor
def run_rebuild(args):
    """
    Run the rebuild process with monitoring and error handling.
    
    Args:
        args: Command-line arguments
    """
    logger.info("Starting enhanced vector store rebuild...")
    
    # Check if a rebuild is already running
    if is_rebuild_running():
        logger.error("A rebuild process is already running. Exiting.")
        return False
    
    # Write the PID file
    write_pid_file()
    
    try:
        # Set up signal handlers
        setup_signal_handlers()
        
        # Start the continuous rebuild process
        start_time = time.time()
        
        # Run the continuous rebuild process with our enhanced options
        success = continuous_rebuild(
            max_chunks=args.max_chunks,
            delay_seconds=args.delay,
            enable_monitoring=not args.no_monitoring,
            start_from_checkpoint=not args.no_checkpoint,
            retry_failed=not args.no_retry
        )
        
        # Calculate elapsed time
        elapsed_time = time.time() - start_time
        hours, remainder = divmod(elapsed_time, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        # Get final statistics
        progress = check_progress(json_output=True)
        error_stats = get_error_stats()
        
        # Log completion
        if success:
            logger.info("=" * 60)
            logger.info("REBUILD PROCESS COMPLETED SUCCESSFULLY")
            logger.info("=" * 60)
            logger.info(f"Total time: {int(hours)}h {int(minutes)}m {int(seconds)}s")
            logger.info(f"Chunks processed: {progress['vector_chunks']}/{progress['db_chunks']} "
                       f"({progress['progress_percent']:.1f}%)")
            
            if error_stats["total_errors"] > 0:
                logger.info(f"Total errors encountered: {error_stats['total_errors']} "
                          f"({error_stats['recoverable_errors']} recoverable, "
                          f"{error_stats['unrecoverable_errors']} unrecoverable)")
            else:
                logger.info("No errors encountered during rebuild")
            
            logger.info("=" * 60)
            
            return True
        else:
            logger.error("=" * 60)
            logger.error("REBUILD PROCESS FAILED")
            logger.error("=" * 60)
            logger.error(f"Total time: {int(hours)}h {int(minutes)}m {int(seconds)}s")
            logger.error(f"Chunks processed: {progress['vector_chunks']}/{progress['db_chunks']} "
                        f"({progress['progress_percent']:.1f}%)")
            logger.error(f"Total errors encountered: {error_stats['total_errors']} "
                        f"({error_stats['recoverable_errors']} recoverable, "
                        f"{error_stats['unrecoverable_errors']} unrecoverable)")
            
            # Show retryable documents
            retryable_docs = get_retryable_documents()
            if retryable_docs:
                logger.error(f"Documents that can be retried: {len(retryable_docs)}")
                logger.error(f"Example document IDs: {retryable_docs[:5]}")
            
            logger.error("=" * 60)
            
            return False
    
    except Exception as e:
        logger.error(f"Fatal error in rebuild process: {str(e)}")
        logger.error(traceback.format_exc())
        return False
    
    finally:
        # Clean up resources
        stop_monitoring()
        remove_pid_file()

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Enhanced vector store rebuild with monitoring and error handling")
    parser.add_argument("--max-chunks", type=int, default=None, 
                      help="Maximum number of chunks to process")
    parser.add_argument("--delay", type=float, default=1.5, 
                      help="Delay between chunks in seconds (default: 1.5)")
    parser.add_argument("--no-monitoring", action="store_true", 
                      help="Disable monitoring system")
    parser.add_argument("--no-checkpoint", action="store_true", 
                      help="Don't resume from the last checkpoint")
    parser.add_argument("--no-retry", action="store_true", 
                      help="Don't retry previously failed documents")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Run the rebuild process
    success = run_rebuild(args)
    
    # Exit with appropriate status code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()