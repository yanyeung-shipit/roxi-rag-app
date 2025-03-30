#!/usr/bin/env python3
"""
Monitor the progress of vector store rebuilding.
This script provides real-time updates on the processing progress.
"""

import os
import sys
import time
import json
import signal
import pickle
from typing import Set, Dict, Any, Optional
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Constants
REFRESH_INTERVAL = 5  # seconds
DOCUMENT_DATA_FILE = "document_data.pkl"
PROCESS_PID_FILE = "rebuild_process.pid"
TARGET_PERCENTAGE = 75.0

class ProgressMonitor:
    """Monitor progress of the vector store rebuilding process."""
    
    def __init__(self):
        """Initialize the progress monitor."""
        self.running = True
        self.start_time = time.time()
        self.last_count = 0
        self.last_time = self.start_time
        self.processing_rate = 0.0
        
    def get_pid(self) -> Optional[int]:
        """Get the PID of the rebuild process if available."""
        if os.path.exists(PROCESS_PID_FILE):
            try:
                with open(PROCESS_PID_FILE, 'r') as f:
                    return int(f.read().strip())
            except:
                return None
        return None
    
    def check_process_running(self) -> bool:
        """Check if the rebuild process is still running."""
        pid = self.get_pid()
        if pid is None:
            return False
            
        try:
            # Send signal 0 to check if process exists
            os.kill(pid, 0)
            return True
        except:
            return False
            
    def get_processed_chunk_ids(self) -> Set[int]:
        """Get the IDs of chunks that have already been processed."""
        processed_ids = set()
        
        try:
            if os.path.exists(DOCUMENT_DATA_FILE):
                with open(DOCUMENT_DATA_FILE, 'rb') as f:
                    loaded_data = pickle.load(f)
                    documents = loaded_data.get('documents', {})
                    
                    # Extract chunk IDs from metadata
                    for doc_id, doc_info in documents.items():
                        metadata = doc_info.get('metadata', {})
                        if 'chunk_id' in metadata and metadata['chunk_id'] is not None:
                            try:
                                chunk_id = int(metadata['chunk_id'])
                                processed_ids.add(chunk_id)
                            except (ValueError, TypeError):
                                pass
        except Exception as e:
            logger.error(f"Error getting processed chunk IDs: {e}")
        
        return processed_ids
    
    def get_progress(self) -> Dict[str, Any]:
        """Get current progress information."""
        try:
            from app import app, db
            from models import DocumentChunk
            from sqlalchemy import func
            
            # Vector store processed chunks
            processed_ids = self.get_processed_chunk_ids()
            processed_count = len(processed_ids)
            
            # Calculate processing rate
            current_time = time.time()
            elapsed = current_time - self.last_time
            
            if elapsed > 0 and processed_count > self.last_count:
                count_diff = processed_count - self.last_count
                rate = count_diff / elapsed
                # Use exponential moving average for smoothing
                if self.processing_rate == 0:
                    self.processing_rate = rate
                else:
                    self.processing_rate = 0.7 * self.processing_rate + 0.3 * rate
                
                self.last_count = processed_count
                self.last_time = current_time
            
            with app.app_context():
                # Database total chunks
                total_chunks = db.session.query(func.count(DocumentChunk.id)).scalar()
                
                # Calculate percentages
                if total_chunks > 0:
                    percentage = (processed_count / total_chunks) * 100
                    target_count = int(total_chunks * TARGET_PERCENTAGE / 100)
                    remaining = target_count - processed_count
                    
                    # Estimate time remaining
                    if remaining > 0 and self.processing_rate > 0:
                        est_seconds = remaining / self.processing_rate
                        est_minutes = est_seconds // 60
                        est_hours = est_minutes // 60
                        est_minutes %= 60
                        
                        time_estimate = f"{int(est_hours)}h {int(est_minutes)}m"
                    else:
                        time_estimate = "Unknown"
                else:
                    percentage = 0
                    target_count = 0
                    remaining = 0
                    time_estimate = "N/A"
                
                # Calculate elapsed time
                elapsed_total = current_time - self.start_time
                elapsed_hours = int(elapsed_total // 3600)
                elapsed_minutes = int((elapsed_total % 3600) // 60)
                
                result = {
                    "vector_store": processed_count,
                    "database": total_chunks,
                    "percentage": round(percentage, 1),
                    "target_count": target_count,
                    "remaining": max(0, target_count - processed_count),
                    "time_estimate": time_estimate,
                    "processing_rate": round(self.processing_rate, 2),
                    "elapsed_time": f"{elapsed_hours}h {elapsed_minutes}m",
                    "process_running": self.check_process_running()
                }
                
                return result
        except Exception as e:
            logger.error(f"Error getting progress: {e}")
            return {
                "error": str(e),
                "vector_store": 0,
                "database": 0,
                "percentage": 0,
                "process_running": self.check_process_running()
            }
    
    def display_progress(self, progress: Dict[str, Any]):
        """Display progress information in a formatted way."""
        # Clear screen (for cleaner display)
        os.system('clear')
        
        # Check if process is running
        process_status = "RUNNING" if progress.get("process_running", False) else "STOPPED"
        
        # Display progress bar
        percentage = progress.get("percentage", 0)
        bar_length = 30
        filled_length = int(percentage / 100 * bar_length)
        bar = "█" * filled_length + "▒" * (bar_length - filled_length)
        
        print(f"\n  ROXI Vector Store Rebuild Progress Monitor")
        print(f"  =========================================")
        print(f"\n  Status: {process_status}")
        print(f"  Progress: [{bar}] {percentage:.1f}%")
        print(f"\n  Processed: {progress.get('vector_store', 0)}/{progress.get('database', 0)} chunks")
        print(f"  Target: {TARGET_PERCENTAGE:.1f}% ({progress.get('target_count', 0)} chunks)")
        print(f"  Remaining: {progress.get('remaining', 0)} chunks")
        print(f"\n  Processing rate: {progress.get('processing_rate', 0):.2f} chunks/second")
        print(f"  Elapsed time: {progress.get('elapsed_time', '0h 0m')}")
        print(f"  Estimated completion: {progress.get('time_estimate', 'Unknown')}")
        print(f"\n  Press Ctrl+C to exit\n")
    
    def signal_handler(self, sig, frame):
        """Handle interrupt signal."""
        print("\nMonitoring stopped.")
        self.running = False
        sys.exit(0)
        
    def run(self):
        """Run the monitoring loop."""
        # Set up signal handler for clean exit
        signal.signal(signal.SIGINT, self.signal_handler)
        
        logger.info("Starting progress monitoring...")
        logger.info(f"Refresh interval: {REFRESH_INTERVAL} seconds")
        logger.info("Press Ctrl+C to stop monitoring")
        
        try:
            while self.running:
                progress = self.get_progress()
                self.display_progress(progress)
                
                # Check if we've reached the target
                if progress.get("percentage", 0) >= TARGET_PERCENTAGE:
                    print("\nTarget percentage reached! Monitoring complete.")
                    break
                    
                # Check if process is still running
                if not progress.get("process_running", False):
                    process_count = progress.get("vector_store", 0)
                    print(f"\nRebuild process has stopped after processing {process_count} chunks.")
                    print("You can restart it with: ./run_to_75_percent.sh")
                    break
                
                time.sleep(REFRESH_INTERVAL)
                
        except KeyboardInterrupt:
            print("\nMonitoring stopped.")
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")
            
        return

def main():
    """Main function."""
    monitor = ProgressMonitor()
    monitor.run()

if __name__ == "__main__":
    main()