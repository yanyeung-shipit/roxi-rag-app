#!/usr/bin/env python3
"""
Run Chunk Processor - Continuous Background Processing Script

This script launches the chunk processor in a loop, ensuring that it keeps running 
even if it crashes or encounters errors. It will process chunks in batches until
a target percentage is reached.
"""

import os
import sys
import time
import datetime
import logging
import subprocess
from typing import List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"continuous_processor_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    ]
)
logger = logging.getLogger(__name__)

# Configuration
MAX_RETRIES = 10
RETRY_DELAY = 30  # seconds
TARGET_PERCENTAGE = 75.0
BATCH_SIZE = 1
PROCESS_DELAY = 3  # seconds


def run_processor(target: float, batch_size: int, delay: int) -> int:
    """
    Run the resilient processor with the given parameters.
    
    Args:
        target: Target percentage to reach
        batch_size: Number of chunks to process per batch
        delay: Delay between batches in seconds
        
    Returns:
        int: Exit code of the process
    """
    logger.info(f"Starting resilient processor with target={target}%, batch_size={batch_size}, delay={delay}s")
    
    cmd = [
        "python", "resilient_processor.py",
        "--target", str(target),
        "--batch-size", str(batch_size),
        "--delay", str(delay)
    ]
    
    logger.info(f"Running command: {' '.join(cmd)}")
    
    try:
        process = subprocess.run(cmd, capture_output=True, text=True, check=False)
        
        if process.returncode != 0:
            logger.error(f"Process failed with exit code {process.returncode}")
            logger.error(f"STDOUT: {process.stdout[:500]}...")
            logger.error(f"STDERR: {process.stderr[:500]}...")
        else:
            logger.info("Process completed successfully")
            
        return process.returncode
    except Exception as e:
        logger.error(f"Error running process: {str(e)}")
        return -1


def check_progress() -> float:
    """
    Check current vector store progress.
    
    Returns:
        float: Current percentage of completion
    """
    try:
        cmd = ["python", "check_progress.py", "--json"]
        process = subprocess.run(cmd, capture_output=True, text=True, check=False)
        
        if process.returncode != 0:
            logger.error(f"Failed to check progress: {process.stderr}")
            return 0.0
            
        # Parse the output and extract the percentage
        output = process.stdout.strip()
        import json
        try:
            data = json.loads(output)
            percentage = data.get("percentage", 0.0)
            logger.info(f"Current progress: {percentage}%")
            return float(percentage)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse progress output: {output}")
            return 0.0
    except Exception as e:
        logger.error(f"Error checking progress: {str(e)}")
        return 0.0


def continuous_processor(target_percentage: float, batch_size: int, delay: int) -> None:
    """
    Run the processor continuously until target percentage is reached.
    
    Args:
        target_percentage: Target percentage to reach
        batch_size: Number of chunks to process per batch
        delay: Delay between batches in seconds
    """
    logger.info(f"Starting continuous processor with target {target_percentage}%")
    
    retries = 0
    
    while True:
        # Check current progress
        current_percentage = check_progress()
        
        # If we've reached the target, we're done
        if current_percentage >= target_percentage:
            logger.info(f"Target percentage of {target_percentage}% reached! Current: {current_percentage}%")
            break
            
        # Run the processor
        exit_code = run_processor(target_percentage, batch_size, delay)
        
        # If the process exited successfully, we're done
        if exit_code == 0:
            logger.info("Processor completed successfully")
            break
            
        # If the process failed, retry after a delay
        retries += 1
        
        if retries >= MAX_RETRIES:
            logger.error(f"Maximum retries ({MAX_RETRIES}) reached, giving up")
            break
            
        logger.info(f"Retry {retries}/{MAX_RETRIES} after {RETRY_DELAY} seconds")
        time.sleep(RETRY_DELAY)
    
    logger.info("Continuous processor finished")


if __name__ == "__main__":
    # Parse command line arguments if given, otherwise use defaults
    import argparse
    parser = argparse.ArgumentParser(description='Run chunk processor continuously')
    parser.add_argument('--target', type=float, default=TARGET_PERCENTAGE,
                      help=f'Target percentage to reach (default: {TARGET_PERCENTAGE})')
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE,
                      help=f'Number of chunks to process per batch (default: {BATCH_SIZE})')
    parser.add_argument('--delay', type=int, default=PROCESS_DELAY,
                      help=f'Delay between batches in seconds (default: {PROCESS_DELAY})')
    
    args = parser.parse_args()
    
    # Run continuously
    continuous_processor(
        target_percentage=args.target,
        batch_size=args.batch_size,
        delay=args.delay
    )