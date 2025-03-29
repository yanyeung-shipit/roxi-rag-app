#!/bin/bash

# process_next_batch.sh
# Process the next batch of chunks in a single run
# Designed to be run periodically or manually to make steady progress

# Default batch size
BATCH_SIZE=${1:-8}

# Ensure logs directory exists
mkdir -p logs/batch_processing

# Get timestamp for logging
TIMESTAMP=$(date "+%Y%m%d_%H%M%S")
LOG_FILE="logs/batch_processing/batch_${TIMESTAMP}.log"

# Check progress before processing
echo "======================================================" > "$LOG_FILE"
echo "BATCH PROCESSING START: $TIMESTAMP" >> "$LOG_FILE"
echo "Batch size: $BATCH_SIZE" >> "$LOG_FILE"
echo "======================================================" >> "$LOG_FILE"
echo "Initial state:" >> "$LOG_FILE"
python check_progress.py --json >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Process the batch with a timeout
echo "Processing batch of $BATCH_SIZE chunks..." >> "$LOG_FILE"
START_TIME=$(date +%s)
timeout 120 ./run_batch_processor.sh "$BATCH_SIZE" >> "$LOG_FILE" 2>&1
RESULT=$?
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# Log the result
echo "======================================================" >> "$LOG_FILE"
if [ $RESULT -eq 124 ]; then
    echo "⚠️ Batch processing timed out after ${DURATION}s" >> "$LOG_FILE"
    echo "Some chunks may have been processed successfully." >> "$LOG_FILE"
elif [ $RESULT -eq 0 ]; then
    echo "✅ Batch processing completed successfully in ${DURATION}s" >> "$LOG_FILE"
else
    echo "❌ Batch processing failed with exit code $RESULT after ${DURATION}s" >> "$LOG_FILE"
fi

# Check progress after processing
echo "======================================================" >> "$LOG_FILE"
echo "Final state:" >> "$LOG_FILE"
python check_progress.py --json >> "$LOG_FILE"
echo "======================================================" >> "$LOG_FILE"

# Print a summary
echo "Batch processing completed in ${DURATION}s with exit code $RESULT"
echo "Log file: $LOG_FILE"

# If run in a cron job, we can exit here
# For manual use, display progress
python check_progress.py