#!/bin/bash

# Run the chunk processor in the background with nohup to reach 75% completion
# Usage: ./background_run_until_75_percent.sh [batch_size] [delay_seconds]

# Default values
BATCH_SIZE=${1:-5}
DELAY_SECONDS=${2:-3}
LOG_FILE="process_75_percent_background.log"

echo "Starting chunk processor in background to reach 75% target..."
echo "Using batch size: $BATCH_SIZE with $DELAY_SECONDS seconds delay between batches"
echo "Log file: $LOG_FILE"

# Run in the background with nohup
nohup python run_chunk_processor.py --batch-size $BATCH_SIZE --target 75.0 --delay $DELAY_SECONDS > $LOG_FILE 2>&1 &

# Save the process ID
PID=$!
echo "Process started with PID: $PID"
echo "To check progress, run: tail -f $LOG_FILE"
echo "To stop the process, run: kill $PID"