#!/usr/bin/env python3
"""
Monitor the progress of the vector store rebuild process.
This script provides detailed statistics and can automatically restart
the process if needed.
"""

import os
import sys
import time
import logging
import datetime
import argparse
import subprocess
from typing import Dict, Any, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the project root to path to import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import required modules
from app import db, app
from models import Document, DocumentChunk
from utils.vector_store import VectorStore

# Constants
DEFAULT_TARGET_PERCENTAGE = 66.0
PID_FILE = "logs/batch_processing/background_rebuild.pid"
CHECK_INTERVAL = 60  # seconds between progress checks
INACTIVITY_THRESHOLD = 300  # seconds of no progress before considering stalled

def get_vector_store_stats() -> Dict[str, Any]:
    """
    Get current statistics about the vector store.
    
    Returns:
        dict: Statistics including progress percentage, chunks processed, etc.
    """
    with app.app_context():
        # Get database counts
        total_chunks = db.session.query(DocumentChunk).count()
        total_documents = db.session.query(Document).count()
        
        # Get vector store counts
        vector_store = VectorStore()
        processed_chunks = len(vector_store.documents)
        
        # Calculate progress
        percentage = round(processed_chunks / total_chunks * 100, 1) if total_chunks > 0 else 0
        remaining_chunks = total_chunks - processed_chunks
        
        # Estimate remaining time
        # We'll use a conservative estimate of 1 second per chunk
        seconds_remaining = remaining_chunks
        
        # Format time for display
        hours, remainder = divmod(seconds_remaining, 3600)
        minutes, seconds = divmod(remainder, 60)
        time_str = f"{int(hours)}h {int(minutes)}m"
        
        return {
            "total_chunks": total_chunks,
            "total_documents": total_documents,
            "processed_chunks": processed_chunks,
            "percentage": percentage,
            "remaining_chunks": remaining_chunks,
            "estimated_time_remaining": time_str,
            "timestamp": datetime.datetime.now().isoformat()
        }

def get_rebuild_process_info() -> Optional[Dict[str, Any]]:
    """
    Get information about the currently running rebuild process.
    
    Returns:
        dict or None: Process information if running, None otherwise
    """
    if not os.path.exists(PID_FILE):
        return None
    
    try:
        with open(PID_FILE, 'r') as f:
            pid = int(f.read().strip())
        
        # Check if process is running
        try:
            os.kill(pid, 0)  # This will raise OSError if process doesn't exist
            
            # Get process info
            proc_info = subprocess.check_output(
                f"ps -p {pid} -o pid,ppid,cmd,%cpu,%mem,etime", 
                shell=True, 
                universal_newlines=True
            )
            
            # Parse process info
            lines = proc_info.strip().split('\n')
            if len(lines) >= 2:
                headers = lines[0].split()
                values = lines[1].split(None, len(headers) - 1)
                
                process_info = dict(zip(headers, values))
                return {
                    "pid": pid,
                    "running": True,
                    "command": process_info.get("CMD", ""),
                    "cpu_usage": process_info.get("%CPU", ""),
                    "memory_usage": process_info.get("%MEM", ""),
                    "elapsed_time": process_info.get("ELAPSED", "")
                }
            
            return {"pid": pid, "running": True}
        except (OSError, subprocess.SubprocessError):
            return {"pid": pid, "running": False}
    except Exception as e:
        logger.error(f"Error getting process info: {str(e)}")
        return None

def start_rebuild_process(batch_size: int = 5) -> Optional[int]:
    """
    Start a new rebuild process.
    
    Args:
        batch_size: Size of the batch to process
        
    Returns:
        int or None: PID of the new process if successful, None otherwise
    """
    try:
        # Make sure the logs directory exists
        os.makedirs("logs/batch_processing", exist_ok=True)
        
        # Get timestamp for log file
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = f"logs/batch_processing/auto_rebuild_{timestamp}.log"
        
        # Start the process
        cmd = f"nohup python process_to_sixty_six_percent.py --batch-size {batch_size} > {log_file} 2>&1 &"
        subprocess.run(cmd, shell=True, check=True)
        
        # Get the PID (this is a bit of a hack but works in most cases)
        time.sleep(1)  # Wait a moment for the process to start
        ps_output = subprocess.check_output(
            "ps -eo pid,command | grep process_to_sixty_six_percent.py | grep -v grep",
            shell=True,
            universal_newlines=True
        )
        
        if ps_output:
            pid = int(ps_output.strip().split()[0])
            
            # Write the PID file
            with open(PID_FILE, 'w') as f:
                f.write(str(pid))
                
            logger.info(f"Started rebuild process with PID {pid}")
            return pid
        else:
            logger.error("Failed to find PID of new process")
            return None
    except Exception as e:
        logger.error(f"Error starting rebuild process: {str(e)}")
        return None

def monitor_progress(
    auto_restart: bool = False,
    target_percentage: float = DEFAULT_TARGET_PERCENTAGE,
    check_interval: int = CHECK_INTERVAL,
    batch_size: int = 5
) -> None:
    """
    Monitor the progress of the rebuild process.
    
    Args:
        auto_restart: Whether to automatically restart the process if it stops
        target_percentage: Target percentage to reach
        check_interval: Seconds between progress checks
        batch_size: Batch size to use if restarting
    """
    logger.info(f"Starting progress monitoring (auto-restart: {auto_restart})")
    
    last_stats = None
    inactivity_counter = 0
    
    try:
        while True:
            # Get current stats
            stats = get_vector_store_stats()
            
            # Print progress
            print("\n" + "=" * 50)
            print(f"VECTOR STORE REBUILD PROGRESS - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 50)
            print(f"Vector store:   {stats['processed_chunks']} chunks")
            print(f"Database:       {stats['total_chunks']} chunks in {stats['total_documents']} documents")
            print("-" * 50)
            print(f"Progress:       {stats['processed_chunks']}/{stats['total_chunks']} chunks")
            print(f"                {stats['percentage']}% complete")
            print(f"Remaining:      {stats['remaining_chunks']} chunks")
            print(f"Est. time:      {stats['estimated_time_remaining']} remaining")
            
            # Check process status
            process_info = get_rebuild_process_info()
            if process_info:
                status = "RUNNING" if process_info.get("running", False) else "STOPPED"
                print("-" * 50)
                print(f"Process:        PID {process_info.get('pid', 'unknown')} - {status}")
                if process_info.get("running", False) and process_info.get("elapsed_time"):
                    print(f"Running time:    {process_info.get('elapsed_time')}")
                    print(f"CPU/Memory:      {process_info.get('cpu_usage', '0')}% CPU, {process_info.get('memory_usage', '0')}% MEM")
            else:
                print("-" * 50)
                print("Process:        Not running")
            
            print("=" * 50)
            
            # Check if target percentage is reached
            if stats['percentage'] >= target_percentage:
                logger.info(f"Target percentage of {target_percentage}% reached!")
                if process_info and process_info.get("running", False):
                    logger.info(f"Process is still running (PID {process_info.get('pid')}). Let it complete or stop it manually.")
                break
            
            # Check if process needs to be restarted
            needs_restart = False
            
            if not process_info or not process_info.get("running", False):
                logger.warning("Rebuild process is not running")
                needs_restart = auto_restart
            elif last_stats and stats['processed_chunks'] == last_stats['processed_chunks']:
                inactivity_counter += check_interval
                if inactivity_counter >= INACTIVITY_THRESHOLD:
                    logger.warning(f"No progress for {inactivity_counter} seconds")
                    needs_restart = auto_restart
            else:
                inactivity_counter = 0
            
            if needs_restart:
                logger.info("Attempting to restart the rebuild process")
                
                # Kill the existing process if it's stuck
                if process_info and process_info.get("running", False):
                    try:
                        os.kill(process_info.get("pid"), 15)  # SIGTERM
                        logger.info(f"Sent SIGTERM to PID {process_info.get('pid')}")
                        time.sleep(5)  # Give it time to shut down
                    except OSError:
                        pass  # Process already died
                
                # Remove the PID file if it exists
                if os.path.exists(PID_FILE):
                    os.remove(PID_FILE)
                
                # Start a new process
                new_pid = start_rebuild_process(batch_size=batch_size)
                if new_pid:
                    logger.info(f"Successfully restarted rebuild process with PID {new_pid}")
                    inactivity_counter = 0
                else:
                    logger.error("Failed to restart rebuild process")
            
            # Save current stats for comparison
            last_stats = stats
            
            # Wait for next check
            time.sleep(check_interval)
            
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
    except Exception as e:
        logger.error(f"Error in monitoring loop: {str(e)}")
        raise

def main():
    """Main function to start the monitor."""
    parser = argparse.ArgumentParser(description='Monitor vector store rebuild progress')
    parser.add_argument('--auto-restart', action='store_true', help='Automatically restart the process if it stops')
    parser.add_argument('--target', type=float, default=DEFAULT_TARGET_PERCENTAGE,
                        help=f'Target percentage to reach (default: {DEFAULT_TARGET_PERCENTAGE})')
    parser.add_argument('--interval', type=int, default=CHECK_INTERVAL,
                        help=f'Seconds between progress checks (default: {CHECK_INTERVAL})')
    parser.add_argument('--batch-size', type=int, default=5,
                        help='Batch size to use if restarting (default: 5)')
    
    args = parser.parse_args()
    
    monitor_progress(
        auto_restart=args.auto_restart,
        target_percentage=args.target,
        check_interval=args.interval,
        batch_size=args.batch_size
    )

if __name__ == "__main__":
    main()