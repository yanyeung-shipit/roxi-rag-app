#!/usr/bin/env python3
"""
Enhanced Processing to 100 Percent

This script processes chunks until 100% of them are in the vector store,
with enhanced error handling, better checkpointing, and robust database connections.
It's designed to be more resilient to PostgreSQL SSL connection errors.
"""

import os
import sys
import time
import json
import logging
import traceback
import random
from datetime import datetime
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("enhanced_100percent.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Enhanced100PercentProcessor")

# Constants
TARGET_PERCENTAGE = 100.0
CHECKPOINT_FILE = "enhanced_100percent_checkpoint.json"
BATCH_SIZE = 3

def run_enhanced_processor():
    """
    Main function to run the enhanced processor to 100%.
    """
    try:
        # Import the enhanced batch processor
        from enhanced_batch_processor import BatchProcessor
        
        # Create processor with target of 100%
        processor = BatchProcessor(
            batch_size=BATCH_SIZE,
            target_percentage=TARGET_PERCENTAGE
        )
        
        # Run until target
        logger.info(f"Starting enhanced processing to {TARGET_PERCENTAGE}%")
        result = processor.run_until_target()
        
        # Log the results
        logger.info(f"Processing complete!")
        logger.info(f"Initial progress: {result['initial_progress']['percentage_completed']:.2f}%")
        logger.info(f"Final progress: {result['final_progress']['percentage_completed']:.2f}%")
        logger.info(f"Elapsed time: {result['elapsed_time_seconds']/60:.2f} minutes")
        logger.info(f"Processed {result['total_chunks_processed']} chunks in {result['batches_processed']} batches")
        
        # Print success message
        print("\n== PROCESSING COMPLETE ==")
        print(f"Successfully processed chunks to {result['final_progress']['percentage_completed']:.2f}% completion")
        print(f"Target was: {TARGET_PERCENTAGE}%")
        print(f"Total time: {result['elapsed_time_seconds']/60:.2f} minutes")
        
        return 0
        
    except ImportError as e:
        logger.error(f"Error importing BatchProcessor: {str(e)}")
        print(f"Error: Could not import the BatchProcessor.")
        print(f"Please ensure enhanced_batch_processor.py is available in the current directory.")
        return 1
        
    except KeyboardInterrupt:
        logger.info("Processing interrupted by user")
        print("\nProcessing interrupted by user.")
        return 130
        
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}")
        traceback.print_exc()
        print(f"\nError: {str(e)}")
        print("Check enhanced_100percent.log for details.")
        return 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enhanced chunk processor to 100% completion")
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE,
                        help=f"Batch size (default: {BATCH_SIZE})")
    
    args = parser.parse_args()
    BATCH_SIZE = args.batch_size
    
    sys.exit(run_enhanced_processor())