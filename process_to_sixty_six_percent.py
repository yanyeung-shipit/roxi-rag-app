#!/usr/bin/env python3
"""
Process chunks using the batch processor until we reach 66% completion.
This script is a specialized version of batch_rebuild_to_target.py that
sets the target percentage to 66% by default.
"""

import os
import sys
import logging
import time
import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the current directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from batch_rebuild_to_target import BatchProcessor

# Target percentage is 100% to match updated user requirements
TARGET_PERCENTAGE = 100.0

# Default batch size is 5 chunks at a time
DEFAULT_BATCH_SIZE = 5

def process_to_sixty_six_percent(batch_size: int = DEFAULT_BATCH_SIZE):
    """
    Process chunks until 66% completion is reached.
    
    Args:
        batch_size: Number of chunks to process per batch
    """
    start_time = time.time()
    logger.info(f"Starting batch processing to reach {TARGET_PERCENTAGE}% completion")
    
    # Create and run batch processor
    processor = BatchProcessor(batch_size=batch_size, target_percentage=TARGET_PERCENTAGE)
    summary = processor.run_until_target()
    
    # Calculate total time
    elapsed_time = time.time() - start_time
    hours, remainder = divmod(elapsed_time, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    # Log completion summary
    logger.info("=" * 50)
    logger.info("BATCH PROCESSING COMPLETED")
    logger.info("=" * 50)
    logger.info(f"Total elapsed time: {int(hours)}h {int(minutes)}m {int(seconds)}s")
    logger.info(f"Processed {summary['chunks_processed']} chunks in {summary['batches_processed']} batches")
    logger.info(f"Starting percentage: {summary['start_percentage']}%")
    logger.info(f"Final percentage: {summary['final_percentage']}%")
    logger.info(f"Target reached: {'Yes' if summary['reached_target'] else 'No'}")
    logger.info("=" * 50)
    
    return summary

def main():
    """Main function to run the processing."""
    # Parse command-line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Process chunks until 66% completion is reached')
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE,
                        help=f'Number of chunks to process per batch (default: {DEFAULT_BATCH_SIZE})')
    
    args = parser.parse_args()
    
    process_to_sixty_six_percent(batch_size=args.batch_size)

if __name__ == "__main__":
    main()