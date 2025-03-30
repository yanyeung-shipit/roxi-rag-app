#!/usr/bin/env python
"""
Test the processing script for 5 minutes to verify it works correctly.
"""

import os
import sys
import time
import signal
import subprocess
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# How long to run the test for
TEST_DURATION = timedelta(minutes=5)

def main():
    """Run the processor for a limited time to test it."""
    logger.info(f"Starting 5-minute test of the processing script")
    
    # Start the processor
    logger.info("Starting processor...")
    proc = subprocess.Popen(["python", "process_to_50_percent.py"])
    
    # Calculate end time
    start_time = datetime.now()
    end_time = start_time + TEST_DURATION
    
    logger.info(f"Test started at {start_time.strftime('%H:%M:%S')}")
    logger.info(f"Will run until {end_time.strftime('%H:%M:%S')}")
    
    try:
        # Wait until test duration is reached
        while datetime.now() < end_time:
            # Check if the process is still running
            if proc.poll() is not None:
                logger.error(f"Process terminated unexpectedly with code {proc.returncode}")
                return 1
                
            # Show progress update every 30 seconds
            if datetime.now().second % 30 == 0:
                logger.info(f"Still running... ({datetime.now().strftime('%H:%M:%S')})")
                
            # Sleep for a short time
            time.sleep(1)
        
        # Test duration reached
        logger.info(f"Test duration reached, terminating process")
        proc.terminate()
        
        # Wait for process to terminate
        for _ in range(5):
            if proc.poll() is not None:
                break
            time.sleep(1)
        
        # If process is still running, kill it
        if proc.poll() is None:
            logger.warning("Process did not terminate, killing it")
            proc.kill()
        
        # Check progress
        logger.info("Checking final progress...")
        os.system("python check_progress.py")
        
        logger.info("Test completed successfully")
        return 0
        
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
        proc.terminate()
        return 1

if __name__ == "__main__":
    sys.exit(main())