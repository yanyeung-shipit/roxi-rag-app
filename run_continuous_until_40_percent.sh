#!/bin/bash

# Continuous Processor Wrapper - Simplified Version
# This script runs the resilient_processor.py until the target percentage is reached
# If the process dies, it restarts automatically
# Debug version with more error handling

TARGET_PERCENTAGE=40.0
BATCH_SIZE=1
DELAY_SECONDS=3
LOG_FILE="process_40_percent_continuous.log"

echo "Starting continuous processor at $(date)" | tee -a $LOG_FILE
echo "Target: ${TARGET_PERCENTAGE}% completion" | tee -a $LOG_FILE
echo "=======================================" | tee -a $LOG_FILE

# Function to check current progress - using check_progress.py
check_progress() {
    # Use grep to parse the percentage from check_progress.py's output
    progress_output=$(python check_progress.py)
    # Extract just the percentage number (without the % symbol)
    current_percentage=$(echo "$progress_output" | grep -o "[0-9]\+\.[0-9]\+%" | head -1 | sed 's/%//')
    # If no percentage found, default to 0
    if [ -z "$current_percentage" ]; then
        current_percentage="0.0"
    fi
    echo "$current_percentage"
}

# Process one batch of chunks
process_one_batch() {
    echo "Processing one batch at $(date)" | tee -a $LOG_FILE
    
    # Run the processor directly with simplified arguments
    python resilient_processor.py --batch-size $BATCH_SIZE --delay $DELAY_SECONDS --target $TARGET_PERCENTAGE 2>&1 | tee -a $LOG_FILE
    
    # Check exit status
    status=$?
    echo "Process exited with status $status at $(date)" | tee -a $LOG_FILE
    
    # Always sleep a bit to prevent rapid restarts if there's an immediate failure
    sleep 5
    
    return $status
}

# Continue running until target is reached
while true; do
    # Check if we've reached the target
    current=$(check_progress)
    echo "Current progress check: ${current}%" | tee -a $LOG_FILE
    
    # Simple numeric comparison with bc
    if (( $(echo "$current >= $TARGET_PERCENTAGE" | bc -l) )); then
        echo "Target reached: ${current}% complete" | tee -a $LOG_FILE
        break
    fi
    
    echo "Current progress: ${current}% - Target: ${TARGET_PERCENTAGE}%" | tee -a $LOG_FILE
    
    # Process one batch
    process_one_batch
    
    echo "Completed batch processing cycle at $(date)" | tee -a $LOG_FILE
    
    # Small pause between runs
    sleep 2
done

echo "Processing complete! Reached ${current}% at $(date)" | tee -a $LOG_FILE