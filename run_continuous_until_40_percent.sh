#!/bin/bash

# Continuous Processor Wrapper
# This script runs the resilient_processor.py until the target percentage is reached
# If the process dies, it restarts automatically

TARGET_PERCENTAGE=40.0
BATCH_SIZE=1
DELAY_SECONDS=3
LOG_FILE="process_40_percent_continuous.log"

echo "Starting continuous processor at $(date)" | tee -a $LOG_FILE
echo "Target: ${TARGET_PERCENTAGE}% completion" | tee -a $LOG_FILE
echo "=======================================" | tee -a $LOG_FILE

# Function to check current progress
check_progress() {
    progress_output=$(python check_progress.py)
    current_percentage=$(echo "$progress_output" | grep -o '[0-9]*\.[0-9]*%' | head -1 | sed 's/%//')
    echo $current_percentage
}

# Continue running until target is reached
while true; do
    # Check if we've reached the target
    current=$(check_progress)
    
    if (( $(echo "$current >= $TARGET_PERCENTAGE" | bc -l) )); then
        echo "Target reached: ${current}% complete" | tee -a $LOG_FILE
        break
    fi
    
    echo "Current progress: ${current}% - Target: ${TARGET_PERCENTAGE}%" | tee -a $LOG_FILE
    echo "Starting new processor run at $(date)" | tee -a $LOG_FILE
    
    # Run the processor with tee to capture output to log file
    python resilient_processor.py --target $TARGET_PERCENTAGE --batch-size $BATCH_SIZE --delay $DELAY_SECONDS | tee -a $LOG_FILE
    
    # Check exit status
    status=$?
    if [ $status -ne 0 ]; then
        echo "Process exited with status $status at $(date)" | tee -a $LOG_FILE
        echo "Restarting in 5 seconds..." | tee -a $LOG_FILE
        sleep 5
    fi
    
    # Small pause between runs
    sleep 2
done

echo "Processing complete! Reached ${current}% at $(date)" | tee -a $LOG_FILE