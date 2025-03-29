#!/bin/bash

# run_continuous_processor.sh
# Continuously process chunks in small batches until all are processed
# This script is designed to handle Replit timeouts by processing chunks in small batches

# The batch size (number of chunks per batch)
BATCH_SIZE=${1:-5}

# Maximum number of batches to process (to avoid endless loops)
MAX_BATCHES=${2:-100}

# Safety delay between batches to avoid API rate limits and overloading the system
BATCH_DELAY=3

# Maximum time to allow a batch to run (in seconds) before considering it timed out
BATCH_TIMEOUT=120

# Set up logging
LOG_FILE="continuous_processing.log"
echo "======================================================" > "$LOG_FILE"
echo "CONTINUOUS CHUNK PROCESSING" >> "$LOG_FILE"
echo "Batch size: $BATCH_SIZE" >> "$LOG_FILE"
echo "Max batches: $MAX_BATCHES" >> "$LOG_FILE"
echo "Started at: $(date)" >> "$LOG_FILE"
echo "======================================================" >> "$LOG_FILE"

# Function to update the log with batch results
log_batch_results() {
    local BATCH_NUM=$1
    local RESULT=$2
    local DURATION=$3

    echo "------------------------------------------------------" >> "$LOG_FILE"
    echo "Batch $BATCH_NUM completed with exit code $RESULT in ${DURATION}s" >> "$LOG_FILE"
    echo "Current progress:" >> "$LOG_FILE"
    python check_progress.py --json >> "$LOG_FILE" 2>/dev/null
    echo "" >> "$LOG_FILE"
}

# Function to log success/error messages
log_message() {
    local MESSAGE=$1
    echo "[$(date "+%Y-%m-%d %H:%M:%S")] $MESSAGE" >> "$LOG_FILE"
    echo "$MESSAGE"
}

# Make sure scripts are executable
chmod +x batch_process_chunks.py run_batch_processor.sh

# Process batches in a loop
for ((i=1; i<=MAX_BATCHES; i++)); do
    log_message "Starting batch $i of $MAX_BATCHES (size: $BATCH_SIZE)..."
    
    # Check if all chunks are processed
    UNPROCESSED=$(python find_unprocessed_chunks.py --limit 1 2>/dev/null | wc -l)
    if [ "$UNPROCESSED" -eq 0 ]; then
        log_message "All chunks processed! Exiting."
        echo "======================================================" >> "$LOG_FILE"
        echo "ALL CHUNKS PROCESSED!" >> "$LOG_FILE"
        echo "Completed at: $(date)" >> "$LOG_FILE"
        echo "======================================================" >> "$LOG_FILE"
        exit 0
    fi
    
    # Record start time
    START_TIME=$(date +%s)
    
    # Process a batch with timeout protection
    log_message "Running batch processor with timeout of $BATCH_TIMEOUT seconds..."
    timeout $BATCH_TIMEOUT ./run_batch_processor.sh "$BATCH_SIZE"
    RESULT=$?
    
    # Record end time and calculate duration
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    
    # Check if the batch timed out
    if [ $RESULT -eq 124 ]; then
        log_message "⚠️ Batch $i timed out after ${DURATION}s but may have processed some chunks"
    elif [ $RESULT -eq 0 ]; then
        log_message "✅ Batch $i completed successfully in ${DURATION}s"
    else
        log_message "❌ Batch $i failed with exit code $RESULT after ${DURATION}s"
    fi
    
    # Log the results
    log_batch_results $i $RESULT $DURATION
    
    # Get the current progress
    CURRENT_PROGRESS=$(python check_progress.py --json 2>/dev/null | grep -o '"progress_pct": [0-9.]*' | cut -d' ' -f2)
    log_message "Current progress: $CURRENT_PROGRESS%"
    
    # Wait between batches to avoid overloading the system
    log_message "Waiting $BATCH_DELAY seconds before next batch..."
    sleep $BATCH_DELAY
done

log_message "Reached maximum number of batches ($MAX_BATCHES)."
echo "======================================================" >> "$LOG_FILE"
echo "REACHED MAXIMUM BATCHES: $MAX_BATCHES" >> "$LOG_FILE"
echo "Completed at: $(date)" >> "$LOG_FILE"
echo "======================================================" >> "$LOG_FILE"