#!/usr/bin/env python3
"""
Monitor Progress

This script continuously monitors the progress of vector store rebuilding 
and writes the status to a log file.
"""

import os
import sys
import time
import json
import logging
import datetime
import subprocess
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"progress_monitor_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    ]
)
logger = logging.getLogger(__name__)

# Configuration
CHECK_INTERVAL = 60  # seconds


def check_progress() -> Dict[str, Any]:
    """
    Check vector store processing progress.
    
    Returns:
        dict: Progress information
    """
    try:
        cmd = ["python", "check_progress.py", "--json"]
        process = subprocess.run(cmd, capture_output=True, text=True, check=False)
        
        if process.returncode != 0:
            logger.error(f"Failed to check progress: {process.stderr}")
            return {"error": process.stderr}
            
        # Parse the output and extract just the JSON part
        output = process.stdout.strip()
        try:
            # Look for opening brace to find the start of JSON
            json_start = output.find('{')
            json_end = output.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = output[json_start:json_end]
                data = json.loads(json_str)
                return data
            else:
                logger.error(f"No JSON found in output: {output}")
                return {"error": "No JSON found", "percentage_complete": 0, "processed_chunks": 0, "total_chunks": 0}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse progress output: {str(e)}")
            # Provide default values in case of error
            return {"error": f"Failed to parse: {str(e)}", "percentage_complete": 0, "processed_chunks": 0, "total_chunks": 0}
    except Exception as e:
        logger.error(f"Error checking progress: {str(e)}")
        return {"error": str(e), "percentage_complete": 0, "processed_chunks": 0, "total_chunks": 0}


def check_processor_running(pid: int = None) -> bool:
    """
    Check if the processor is still running.
    
    Args:
        pid (int, optional): Process ID to check
        
    Returns:
        bool: True if running, False otherwise
    """
    if pid:
        # Check specific PID
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    else:
        # Check for any resilient_processor.py process
        try:
            cmd = ["ps", "-aux"]
            process = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return "resilient_processor.py" in process.stdout
        except Exception:
            return False


def monitor_progress(interval: int = CHECK_INTERVAL, pid: int = None):
    """
    Continuously monitor progress and log results.
    
    Args:
        interval (int): Interval between checks in seconds
        pid (int, optional): Process ID to monitor
    """
    logger.info(f"Starting progress monitor with {interval}s interval")
    if pid:
        logger.info(f"Monitoring processor PID: {pid}")
    
    start_time = datetime.datetime.now()
    last_percentage = 0
    last_chunks = 0
    
    while True:
        # Get current progress
        progress = check_progress()
        
        # Check if processor is running
        processor_running = check_processor_running(pid)
        
        # Calculate elapsed time
        elapsed = datetime.datetime.now() - start_time
        elapsed_str = str(elapsed).split('.')[0]  # Remove microseconds
        
        # Extract data
        current_percentage = progress.get("percentage_complete", 0)
        processed_chunks = progress.get("processed_chunks", 0)
        total_chunks = progress.get("total_chunks", 0)
        remaining_chunks = progress.get("remaining_chunks", 0)
        
        # Calculate progress changes since last check
        new_chunks = processed_chunks - last_chunks
        percentage_change = current_percentage - last_percentage
        
        # Calculate processing rate and ETA
        chunks_per_minute = 0
        eta = "Unknown"
        
        if elapsed.total_seconds() > 0:
            chunks_per_minute = (processed_chunks * 60) / elapsed.total_seconds()
            
            if chunks_per_minute > 0:
                minutes_remaining = remaining_chunks / chunks_per_minute
                eta_time = datetime.datetime.now() + datetime.timedelta(minutes=minutes_remaining)
                eta = eta_time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Log progress
        logger.info(f"Progress: {processed_chunks}/{total_chunks} chunks ({current_percentage:.2f}%)")
        logger.info(f"Elapsed: {elapsed_str}, New chunks: {new_chunks}, Change: {percentage_change:.2f}%")
        logger.info(f"Rate: {chunks_per_minute:.2f} chunks/minute, ETA: {eta}")
        logger.info(f"Processor running: {processor_running}")
        logger.info("-" * 50)
        
        # Update last values
        last_percentage = current_percentage
        last_chunks = processed_chunks
        
        # Check if complete
        if current_percentage >= 75.0:
            logger.info(f"Target reached! Final progress: {current_percentage:.2f}%")
            break
            
        # Check if processor stopped
        if not processor_running and pid:
            logger.warning(f"Processor (PID {pid}) is no longer running!")
            
        # Wait for next check
        time.sleep(interval)


if __name__ == "__main__":
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Monitor vector store rebuilding progress')
    parser.add_argument('--interval', type=int, default=CHECK_INTERVAL,
                      help=f'Check interval in seconds (default: {CHECK_INTERVAL})')
    parser.add_argument('--pid', type=int, default=None,
                      help='Process ID to monitor')
    
    args = parser.parse_args()
    
    # Start monitoring
    monitor_progress(interval=args.interval, pid=args.pid)