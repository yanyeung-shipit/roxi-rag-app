#!/bin/bash
# Process chunks using our optimized fast chunk processor
# This script runs in the background and continues processing regardless of connection

# Configuration
BATCH_SIZE=3
TARGET_PERCENTAGE=75.0
MAX_BATCHES=10  # Process 10 batches at a time (30 chunks total)
LOG_FILE="process_75_percent_enhanced.log"

echo "Starting fast batch processor with batch size $BATCH_SIZE"
echo "Processing up to $MAX_BATCHES batches (up to $TARGET_PERCENTAGE% completion)"
echo "Log will be written to $LOG_FILE"

nohup python fast_chunk_processor.py --batch-size $BATCH_SIZE --target $TARGET_PERCENTAGE --max-batches $MAX_BATCHES >> $LOG_FILE 2>&1 &

# Save the process ID
echo $! > fast_processor.pid
echo "Started background process with PID: $(cat fast_processor.pid)"
echo "Run 'python check_progress.py' to check the current progress"