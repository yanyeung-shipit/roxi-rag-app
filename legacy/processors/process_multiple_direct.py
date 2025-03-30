#!/usr/bin/env python
"""
Process multiple chunks in sequence using direct_process_chunk.py
This avoids the overhead of starting a new Python process for each chunk.
"""

import sys
import time
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def process_multiple_chunks(start_id, count=5):
    """Process multiple chunks in sequence."""
    
    logger.info(f"Starting to process {count} chunks starting from ID {start_id}")
    
    successful = 0
    failed = 0
    
    for i in range(count):
        chunk_id = start_id + i
        logger.info(f"Processing chunk {i+1}/{count} (ID: {chunk_id})")
        
        start_time = time.time()
        try:
            # Run direct_process_chunk.py for this chunk ID
            result = subprocess.run(
                ["python", "direct_process_chunk.py", str(chunk_id)],
                check=True,
                capture_output=True,
                text=True
            )
            
            duration = time.time() - start_time
            logger.info(f"✅ Successfully processed chunk {chunk_id} in {duration:.2f}s")
            successful += 1
            
            # Show the output
            print(result.stdout)
            
            # Sleep for a moment to avoid rate limiting
            time.sleep(1)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Failed to process chunk {chunk_id}: {e}")
            logger.error(f"Output: {e.stdout}")
            logger.error(f"Error: {e.stderr}")
            failed += 1
    
    logger.info(f"Completed processing {count} chunks")
    logger.info(f"Results: {successful} successful, {failed} failed")
    
    return {"successful": successful, "failed": failed}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python process_multiple_direct.py START_ID [COUNT]")
        sys.exit(1)
    
    start_id = int(sys.argv[1])
    count = 5  # Default
    
    if len(sys.argv) >= 3:
        count = int(sys.argv[2])
    
    result = process_multiple_chunks(start_id, count)
    
    if result["failed"] > 0:
        sys.exit(1)