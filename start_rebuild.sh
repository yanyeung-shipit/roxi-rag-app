#!/bin/bash
# Start the rebuild process for the vector store
# This script will run batches of the rebuild process

# By default, run for 30 minutes or 100 batches, whichever comes first
MAX_TIME=${1:-1800}  # 30 minutes in seconds
MAX_BATCHES=${2:-100}
BATCH_DELAY=${3:-3}  # Delay between batches (seconds)

echo "Starting rebuild process"
echo "Will run for ${MAX_TIME}s or ${MAX_BATCHES} batches, whichever comes first"
echo "Delay between batches: ${BATCH_DELAY}s"

# Create a log directory if it doesn't exist
mkdir -p logs/rebuild

# Get the current timestamp for the log file
TIMESTAMP=$(date +%Y%m%d%H%M%S)
LOG_FILE="logs/rebuild/rebuild_${TIMESTAMP}.log"

echo "Logging to: ${LOG_FILE}"

# Start the timer
START_TIME=$(date +%s)
CURRENT_TIME=$START_TIME
END_TIME=$((START_TIME + MAX_TIME))

# Initialize counters
BATCH_COUNT=0
SUCCESS_COUNT=0

# Run until we've reached the maximum time or maximum batches
while [ $CURRENT_TIME -lt $END_TIME ] && [ $BATCH_COUNT -lt $MAX_BATCHES ]; do
    # Increment the batch counter
    BATCH_COUNT=$((BATCH_COUNT + 1))
    
    # Run a batch
    echo "[$(date)] Running batch ${BATCH_COUNT}/${MAX_BATCHES}" | tee -a $LOG_FILE
    if python3 rebuild_batch.py >> $LOG_FILE 2>&1; then
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        echo "[$(date)] Batch ${BATCH_COUNT} completed successfully" | tee -a $LOG_FILE
    else
        echo "[$(date)] Batch ${BATCH_COUNT} failed" | tee -a $LOG_FILE
    fi
    
    # Check progress
    PROGRESS=$(python3 check_progress.py --json | grep -o '"progress_pct": [0-9.]*' | cut -d' ' -f2)
    echo "[$(date)] Current progress: ${PROGRESS}%" | tee -a $LOG_FILE
    
    # Check if we're done
    if [ "$PROGRESS" == "100.0" ]; then
        echo "[$(date)] All chunks processed, stopping" | tee -a $LOG_FILE
        break
    fi
    
    # Sleep for a bit to avoid hitting rate limits
    echo "[$(date)] Sleeping for ${BATCH_DELAY}s" | tee -a $LOG_FILE
    sleep $BATCH_DELAY
    
    # Update the current time
    CURRENT_TIME=$(date +%s)
done

# Calculate the elapsed time
ELAPSED_TIME=$((CURRENT_TIME - START_TIME))
ELAPSED_MIN=$((ELAPSED_TIME / 60))
ELAPSED_SEC=$((ELAPSED_TIME % 60))

# Print the summary
echo "[$(date)] Rebuild process completed" | tee -a $LOG_FILE
echo "[$(date)] Batches run: ${BATCH_COUNT}, successful: ${SUCCESS_COUNT}" | tee -a $LOG_FILE
echo "[$(date)] Elapsed time: ${ELAPSED_MIN}m ${ELAPSED_SEC}s" | tee -a $LOG_FILE

# Get the final progress
python3 check_progress.py | tee -a $LOG_FILE

echo "Rebuild process complete"
echo "See $LOG_FILE for details"