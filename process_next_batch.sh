#!/bin/bash
# Process the next batch of chunks quickly
# This script takes the last processed chunk ID and processes the next batch

# Configuration
LAST_ID=${1:-6676}  # Default to last ID we processed
BATCH_SIZE=${2:-5}  # Default to 5 chunks per batch
LOG_FILE="logs/batch_processing/batch_$(date +%Y%m%d_%H%M%S).log"

# Create log directory if it doesn't exist
mkdir -p "logs/batch_processing"

# Log the start
echo "======================================================" | tee -a "$LOG_FILE"
echo "BATCH PROCESSING START: $(date +%Y%m%d_%H%M%S)" | tee -a "$LOG_FILE"
echo "Last processed ID: $LAST_ID" | tee -a "$LOG_FILE"
echo "Batch size: $BATCH_SIZE" | tee -a "$LOG_FILE"
echo "======================================================" | tee -a "$LOG_FILE"

# Check initial state
echo "Initial state:" | tee -a "$LOG_FILE"
python check_progress.py | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Get the next chunks to process
echo "Getting next chunks to process after ID $LAST_ID..." | tee -a "$LOG_FILE"
NEXT_CHUNKS=$(python get_next_chunks.py $LAST_ID --limit $BATCH_SIZE)

# Count how many chunks we got
CHUNK_COUNT=$(echo "$NEXT_CHUNKS" | wc -l)
echo "Found $CHUNK_COUNT chunks to process" | tee -a "$LOG_FILE"

# Process each chunk
if [ -n "$NEXT_CHUNKS" ]; then
    echo "Processing $CHUNK_COUNT chunks..." | tee -a "$LOG_FILE"
    echo "$NEXT_CHUNKS" | while read -r chunk_id; do
        echo "Processing chunk $chunk_id..." | tee -a "$LOG_FILE"
        python direct_process_chunk.py $chunk_id | tee -a "$LOG_FILE"
        # Get the last line of the log to confirm success
        LAST_LINE=$(tail -n 1 "$LOG_FILE")
        if [[ $LAST_LINE == *"Processed chunk $chunk_id"* ]]; then
            echo "Successfully processed chunk $chunk_id" | tee -a "$LOG_FILE"
            # Update the last processed ID
            LAST_ID=$chunk_id
        else
            echo "Failed to process chunk $chunk_id, stopping batch" | tee -a "$LOG_FILE"
            break
        fi
    done
else
    echo "No chunks found to process" | tee -a "$LOG_FILE"
fi

# Check final state
echo "" | tee -a "$LOG_FILE"
echo "Final state:" | tee -a "$LOG_FILE"
python check_progress.py | tee -a "$LOG_FILE"

echo "Batch processing completed at $(date)" | tee -a "$LOG_FILE"
echo "Log file: $LOG_FILE"
echo "Last processed ID: $LAST_ID"

# Output the last processed ID for the next run
echo $LAST_ID