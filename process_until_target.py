#!/usr/bin/env python3
"""
Process chunks until reaching a target percentage of completion.
This script uses the reliable single-chunk processing approach
to incrementally add chunks to the vector store.
"""
import os
import subprocess
import time
import sys
import logging
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_current_progress() -> Dict[str, Any]:
    """
    Get the current progress by parsing the output of check_progress.py.
    
    Returns:
        dict: Dictionary containing progress information
    """
    try:
        # Run check_progress.py and capture its output
        result = subprocess.run(
            ["python", "check_progress.py"], 
            capture_output=True, 
            text=True,
            check=True
        )
        
        # Parse the output to extract progress information
        output_lines = result.stdout.strip().split('\n')
        vector_store_line = next((line for line in output_lines if "Vector store:" in line), "")
        database_line = next((line for line in output_lines if "Database:" in line), "")
        progress_line = next((line for line in output_lines if "Progress:" in line), "")
        percentage_line = next((line for line in output_lines if "%" in line), "")
        
        # Extract numeric values
        vector_store_count = int(vector_store_line.split(':')[1].strip().split(' ')[0]) if vector_store_line else 0
        database_count = int(database_line.split(':')[1].strip().split(' ')[0]) if database_line else 0
        percentage = float(percentage_line.strip().split('%')[0]) if percentage_line else 0.0
        
        return {
            "vector_store_count": vector_store_count,
            "database_count": database_count,
            "percentage": percentage
        }
    except Exception as e:
        logger.error(f"Error getting progress: {e}")
        return {
            "vector_store_count": 0,
            "database_count": 0,
            "percentage": 0.0
        }

def process_next_chunk(current_chunk_id: int) -> int:
    """
    Process the next chunk after the given ID.
    
    Args:
        current_chunk_id: The current chunk ID to process
        
    Returns:
        int: The next chunk ID to process, or the same if processing failed
    """
    try:
        logger.info(f"Processing chunk {current_chunk_id}...")
        # Run the direct chunk processing script which is more reliable
        result = subprocess.run(
            ["python", "direct_process_chunk.py", str(current_chunk_id)],
            check=True,
            capture_output=True,
            text=True
        )
        
        # Check for successful processing in the output
        if "Processed chunk" in result.stdout and "✓" in result.stdout:
            logger.info(f"Successfully processed chunk {current_chunk_id}")
            return current_chunk_id + 1
        else:
            logger.warning(f"Chunk {current_chunk_id} may not have been processed correctly")
            # Try to parse processing time for debugging
            if "in " in result.stdout:
                processing_time = result.stdout.split("in ")[1].split("s")[0]
                logger.info(f"Processing took {processing_time} seconds")
            return current_chunk_id
    except subprocess.CalledProcessError as e:
        logger.error(f"Error processing chunk {current_chunk_id}: {e}")
        if e.stdout:
            logger.error(f"Output: {e.stdout}")
        if e.stderr:
            logger.error(f"Error output: {e.stderr}")
        # Return the same ID so we can retry
        return current_chunk_id
    except Exception as e:
        logger.error(f"Unexpected error processing chunk {current_chunk_id}: {e}")
        return current_chunk_id

def main():
    """
    Main function to process chunks until target percentage is reached.
    """
    # Parse command line arguments
    target_percentage = 65.0
    if len(sys.argv) > 1:
        try:
            target_percentage = float(sys.argv[1])
        except ValueError:
            logger.error(f"Invalid target percentage: {sys.argv[1]}. Using default: 65.0%")
    
    # Get current progress
    progress = get_current_progress()
    current_percentage = progress["percentage"]
    logger.info(f"Starting at {current_percentage:.1f}% complete")
    logger.info(f"Target: {target_percentage:.1f}%")
    
    # Start with the next chunk ID
    # We know the last processed chunk was 6690, so next is 6691
    next_chunk_id = 6691
    
    # Process chunks until target is reached
    while current_percentage < target_percentage:
        start_time = time.time()
        
        # Process the next chunk
        next_chunk_id = process_next_chunk(next_chunk_id)
        
        # Get updated progress
        progress = get_current_progress()
        current_percentage = progress["percentage"]
        
        # Calculate and log processing speed
        elapsed_time = time.time() - start_time
        logger.info(f"Current progress: {current_percentage:.1f}% ({progress['vector_store_count']}/{progress['database_count']} chunks)")
        logger.info(f"Processing speed: {elapsed_time:.2f} seconds per chunk")
        logger.info(f"Remaining to target: {target_percentage - current_percentage:.1f}%")
        
        # Short delay to avoid overwhelming the system
        time.sleep(1)
    
    logger.info(f"Target reached! Current progress: {current_percentage:.1f}%")
    logger.info(f"Processed {progress['vector_store_count']} out of {progress['database_count']} chunks")

if __name__ == "__main__":
    main()