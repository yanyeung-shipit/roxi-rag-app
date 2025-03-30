#!/bin/bash
# Script to run the 75% processing in the background with increased resilience
# This version will retry up to 3 times if the process fails

# Configuration
MAX_RETRIES=3
BATCH_SIZE=5  # Reduced batch size to avoid timeouts
TARGET_PERCENTAGE=75
SLEEP_BETWEEN_RETRIES=30
LOG_FILE="process_75_percent_enhanced.log"

# Echo with timestamp function
timestamp() {
  date +"%Y-%m-%d %H:%M:%S"
}

echo "$(timestamp) Starting vector store rebuild to $TARGET_PERCENTAGE% target" > $LOG_FILE
echo "$(timestamp) Current progress:" >> $LOG_FILE
python check_progress.py >> $LOG_FILE 2>&1

# Track retries
retry_count=0
success=false

while [ $retry_count -lt $MAX_RETRIES ] && [ "$success" != "true" ]; do
    # Increment retry counter
    retry_count=$((retry_count + 1))
    
    echo "$(timestamp) [Attempt $retry_count/$MAX_RETRIES] Running process_to_75_percent.py with batch size $BATCH_SIZE" >> $LOG_FILE
    
    # Start the process
    python process_to_75_percent.py --batch-size $BATCH_SIZE --target-percentage $TARGET_PERCENTAGE >> $LOG_FILE 2>&1
    
    # Check exit status
    if [ $? -eq 0 ]; then
        echo "$(timestamp) Process completed successfully!" >> $LOG_FILE
        success=true
    else
        echo "$(timestamp) Process failed or timed out on attempt $retry_count" >> $LOG_FILE
        
        # Check progress
        echo "$(timestamp) Checking current progress:" >> $LOG_FILE
        python check_progress.py >> $LOG_FILE 2>&1
        
        # Extract progress from check_progress.py output
        current_percentage=$(grep "complete" $LOG_FILE | tail -1 | awk '{print $2}' | sed 's/%//')
        
        # Check if we've reached the target
        if (( $(echo "$current_percentage >= $TARGET_PERCENTAGE" | bc -l) )); then
            echo "$(timestamp) Target percentage of $TARGET_PERCENTAGE% has been reached despite process failure!" >> $LOG_FILE
            success=true
        else
            # Wait before retrying
            echo "$(timestamp) Waiting $SLEEP_BETWEEN_RETRIES seconds before next attempt..." >> $LOG_FILE
            sleep $SLEEP_BETWEEN_RETRIES
        fi
    fi
done

# Final progress check
echo "$(timestamp) Final progress check:" >> $LOG_FILE
python check_progress.py >> $LOG_FILE 2>&1

if [ "$success" = "true" ]; then
    echo "$(timestamp) Vector store rebuild process completed successfully to target $TARGET_PERCENTAGE%!" >> $LOG_FILE
    echo "Vector store rebuild completed successfully to target $TARGET_PERCENTAGE%!"
else
    echo "$(timestamp) Vector store rebuild failed after $MAX_RETRIES attempts." >> $LOG_FILE
    echo "Vector store rebuild failed after $MAX_RETRIES attempts. Check $LOG_FILE for details."
fi

# Print final instructions
echo "You can check the current progress using: python check_progress.py"