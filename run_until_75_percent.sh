#!/bin/bash
# Script to run the 75% processing in the background

# Log file
LOG_FILE="process_75_percent.log"

# Echo with timestamp function
timestamp() {
  date +"%Y-%m-%d %H:%M:%S"
}

echo "$(timestamp) Starting vector store rebuild to 75% target" > $LOG_FILE
echo "$(timestamp) Current progress:" >> $LOG_FILE
python check_progress.py >> $LOG_FILE 2>&1

echo "$(timestamp) Running process_to_75_percent.py with batch size 10" >> $LOG_FILE
nohup python process_to_75_percent.py --batch-size 10 --target-percentage 75 >> $LOG_FILE 2>&1 &
PROCESS_PID=$!
echo "$(timestamp) Process started with PID: $PROCESS_PID" >> $LOG_FILE

echo "Process started with PID: $PROCESS_PID. Check $LOG_FILE for progress."
echo "You can monitor progress using: python check_progress.py"