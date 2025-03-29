#!/usr/bin/env python3
"""
Monitoring script for the vector store rebuild process.
This script can be run at any time to check the progress of the rebuild.
"""
import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Check if the rebuild process is running
def is_rebuild_running():
    """Check if the rebuild process is running."""
    pid_file = "rebuild_process.pid"
    if not os.path.exists(pid_file):
        return False
    
    try:
        with open(pid_file, "r") as f:
            pid = int(f.read().strip())
        
        # Check if the process is running
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, ValueError, OSError):
        return False

# Read the status file
def read_status_file():
    """Read the status file from the monitoring system."""
    status_file = "logs/monitoring/rebuild_status.json"
    if not os.path.exists(status_file):
        return None
    
    try:
        with open(status_file, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return None

# Read the error stats file
def read_error_stats():
    """Read the error statistics from the error handling system."""
    retryable_docs_file = "logs/errors/retryable_documents.json"
    if not os.path.exists(retryable_docs_file):
        return None
    
    try:
        with open(retryable_docs_file, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return None

# Format a timestamp
def format_timestamp(timestamp_str):
    """Format a timestamp string into a human-readable format."""
    if not timestamp_str:
        return "Unknown"
    
    try:
        dt = datetime.fromisoformat(timestamp_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return timestamp_str

# Main function
def main():
    """Main function."""
    # Parse arguments
    parser = argparse.ArgumentParser(description="Monitor the vector store rebuild process")
    parser.add_argument("--refresh", "-r", type=int, default=0,
                      help="Refresh the display every N seconds (0 for no refresh)")
    parser.add_argument("--json", "-j", action="store_true",
                      help="Output in JSON format")
    
    args = parser.parse_args()
    
    # Check if check_progress.py exists, if so use that for statistics
    has_check_progress = os.path.exists("check_progress.py")
    
    # If refresh is enabled, clear the screen and monitor continuously
    if args.refresh > 0:
        try:
            while True:
                # Clear the screen
                os.system("clear" if os.name == "posix" else "cls")
                
                # Run check_progress.py if available
                if has_check_progress:
                    os.system("python3 check_progress.py")
                    print()
                
                # Check if the rebuild is running
                running = is_rebuild_running()
                
                # Print the status
                if running:
                    logger.info("Rebuild process is running")
                else:
                    logger.info("Rebuild process is not running")
                
                # Read the status file
                status = read_status_file()
                if status:
                    # Print the status information
                    progress = status.get("progress", {})
                    monitoring_info = status.get("monitoring_info", {})
                    
                    logger.info("\nRebuild Progress:")
                    logger.info(f"Progress: {progress.get('progress_percent', 0):.1f}% complete")
                    logger.info(f"Chunks: {progress.get('vector_chunks', 0)}/{progress.get('db_chunks', 0)}")
                    logger.info(f"Remaining: {progress.get('chunks_remaining', 0)} chunks")
                    
                    # Print the processing rate if available
                    if progress.get("processing_rate", 0) > 0:
                        rate = progress.get("processing_rate", 0)
                        logger.info(f"Processing rate: {rate:.3f} chunks/second "
                                  f"({rate * 60:.1f} chunks/minute)")
                    
                    # Print the estimated completion time if available
                    if progress.get("estimated_completion_time"):
                        logger.info(f"Estimated completion: {format_timestamp(progress.get('estimated_completion_time'))}")
                        
                        # Calculate remaining time in a human-readable format
                        seconds = progress.get("estimated_seconds_remaining", 0)
                        hours = int(seconds // 3600)
                        minutes = int((seconds % 3600) // 60)
                        
                        logger.info(f"Estimated time remaining: {hours}h {minutes}m")
                    
                    # Print monitoring information
                    logger.info("\nMonitoring Information:")
                    logger.info(f"Start time: {format_timestamp(monitoring_info.get('start_time', ''))}")
                    logger.info(f"Running time: {monitoring_info.get('running_time', 0) / 60:.1f} minutes")
                    logger.info(f"Total checks: {monitoring_info.get('total_checks', 0)}")
                    
                    # Print bottlenecks if any
                    bottlenecks = status.get("bottlenecks", [])
                    if bottlenecks:
                        logger.info("\nBottlenecks Detected:")
                        for bottleneck in bottlenecks:
                            logger.info(f"- {bottleneck.get('type')}: {bottleneck.get('details')}")
                
                # Read error stats
                error_stats = read_error_stats()
                if error_stats:
                    stats = error_stats.get("stats", {})
                    
                    logger.info("\nError Statistics:")
                    logger.info(f"Total errors: {stats.get('total_errors', 0)}")
                    logger.info(f"Recoverable errors: {stats.get('recoverable_errors', 0)}")
                    logger.info(f"Unrecoverable errors: {stats.get('unrecoverable_errors', 0)}")
                    logger.info(f"Retryable documents: {len(error_stats.get('retryable_documents', []))}")
                    logger.info(f"Failed documents: {len(error_stats.get('failed_documents', []))}")
                
                # Check if all chunks are processed
                if status and progress.get("progress_percent", 0) >= 99.9:
                    logger.info("\nRebuild is complete!")
                    if not running:
                        logger.info("Process has exited successfully.")
                        break
                
                # Sleep before refreshing
                time.sleep(args.refresh)
                
        except KeyboardInterrupt:
            logger.info("\nMonitoring stopped by user")
            return
    
    else:
        # Single check, run check_progress.py if available
        if has_check_progress and not args.json:
            os.system("python3 check_progress.py")
            print()
        
        # Check if the rebuild is running
        running = is_rebuild_running()
        
        # Read the status file
        status = read_status_file()
        
        # Read error stats
        error_stats = read_error_stats()
        
        # If JSON output is requested, output everything as JSON
        if args.json:
            output = {
                "running": running,
                "status": status,
                "error_stats": error_stats
            }
            print(json.dumps(output, indent=2))
            return
        
        # Print the status
        if running:
            logger.info("Rebuild process is running")
        else:
            logger.info("Rebuild process is not running")
        
        if status:
            # Print the status information
            progress = status.get("progress", {})
            monitoring_info = status.get("monitoring_info", {})
            
            logger.info("\nRebuild Progress:")
            logger.info(f"Progress: {progress.get('progress_percent', 0):.1f}% complete")
            logger.info(f"Chunks: {progress.get('vector_chunks', 0)}/{progress.get('db_chunks', 0)}")
            logger.info(f"Remaining: {progress.get('chunks_remaining', 0)} chunks")
            
            # Print the processing rate if available
            if progress.get("processing_rate", 0) > 0:
                rate = progress.get("processing_rate", 0)
                logger.info(f"Processing rate: {rate:.3f} chunks/second "
                          f"({rate * 60:.1f} chunks/minute)")
            
            # Print the estimated completion time if available
            if progress.get("estimated_completion_time"):
                logger.info(f"Estimated completion: {format_timestamp(progress.get('estimated_completion_time'))}")
                
                # Calculate remaining time in a human-readable format
                seconds = progress.get("estimated_seconds_remaining", 0)
                hours = int(seconds // 3600)
                minutes = int((seconds % 3600) // 60)
                
                logger.info(f"Estimated time remaining: {hours}h {minutes}m")
            
            # Print monitoring information
            logger.info("\nMonitoring Information:")
            logger.info(f"Start time: {format_timestamp(monitoring_info.get('start_time', ''))}")
            logger.info(f"Running time: {monitoring_info.get('running_time', 0) / 60:.1f} minutes")
            logger.info(f"Total checks: {monitoring_info.get('total_checks', 0)}")
            
            # Print bottlenecks if any
            bottlenecks = status.get("bottlenecks", [])
            if bottlenecks:
                logger.info("\nBottlenecks Detected:")
                for bottleneck in bottlenecks:
                    logger.info(f"- {bottleneck.get('type')}: {bottleneck.get('details')}")
        
        if error_stats:
            stats = error_stats.get("stats", {})
            
            logger.info("\nError Statistics:")
            logger.info(f"Total errors: {stats.get('total_errors', 0)}")
            logger.info(f"Recoverable errors: {stats.get('recoverable_errors', 0)}")
            logger.info(f"Unrecoverable errors: {stats.get('unrecoverable_errors', 0)}")
            logger.info(f"Retryable documents: {len(error_stats.get('retryable_documents', []))}")
            logger.info(f"Failed documents: {len(error_stats.get('failed_documents', []))}")
        
        # Check if all chunks are processed
        if status and progress.get("progress_percent", 0) >= 99.9:
            logger.info("\nRebuild is complete!")

if __name__ == "__main__":
    main()