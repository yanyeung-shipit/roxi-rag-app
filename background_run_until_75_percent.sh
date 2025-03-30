#!/bin/bash
# Script to run the 75% processing in the background with increased resilience
# This version will run in the background using nohup

# Configuration
BATCH_SIZE=5  # Reduced batch size to avoid timeouts
TARGET_PERCENTAGE=75
LOG_FILE="process_75_percent_background.log"

# Echo with timestamp function
timestamp() {
  date +"%Y-%m-%d %H:%M:%S"
}

echo "$(timestamp) Starting vector store rebuild to $TARGET_PERCENTAGE% target" > $LOG_FILE
echo "$(timestamp) Current progress:" >> $LOG_FILE
python check_progress.py >> $LOG_FILE 2>&1

# Start the process in the background
echo "$(timestamp) Running process_to_75_percent.py with batch size $BATCH_SIZE" >> $LOG_FILE
nohup python process_to_75_percent.py --batch-size $BATCH_SIZE --target-percentage $TARGET_PERCENTAGE >> $LOG_FILE 2>&1 &
PROCESS_PID=$!

echo "Process started with PID: $PROCESS_PID. Check $LOG_FILE for progress."
echo "You can monitor progress using: python check_progress.py"