#!/bin/bash
# Process one batch of chunks quickly
# This script is designed to be simple and reliable

# Configuration
BATCH_SIZE=${1:-5}  # Default to 5 chunks, but can be overridden with first argument
LOG_FILE="logs/batch_processing/batch_$(date +%Y%m%d_%H%M%S).log"

# Create log directory if it doesn't exist
mkdir -p "logs/batch_processing"

# Log the start
echo "======================================================" | tee -a "$LOG_FILE"
echo "BATCH PROCESSING START: $(date +%Y%m%d_%H%M%S)" | tee -a "$LOG_FILE"
echo "Batch size: $BATCH_SIZE" | tee -a "$LOG_FILE"
echo "======================================================" | tee -a "$LOG_FILE"

# Check initial state
echo "Initial state:" | tee -a "$LOG_FILE"
python check_progress.py --json | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Process the batch
echo "Processing batch of $BATCH_SIZE chunks..." | tee -a "$LOG_FILE"
python direct_process_chunk.py $(python find_unprocessed_chunks.py --limit 1 | head -n 1) | tee -a "$LOG_FILE"

# If batch size is more than 1, process additional chunks
if [ "$BATCH_SIZE" -gt 1 ]; then
    # Get more chunk IDs and process them
    for i in $(seq 2 $BATCH_SIZE); do
        echo "Processing chunk $i/$BATCH_SIZE..." | tee -a "$LOG_FILE"
        python direct_process_chunk.py $(python find_unprocessed_chunks.py --limit 1 | head -n 1) | tee -a "$LOG_FILE"
    done
fi

# Check final state
echo "" | tee -a "$LOG_FILE"
echo "Final state:" | tee -a "$LOG_FILE"
python check_progress.py | tee -a "$LOG_FILE"

echo "Batch processing completed at $(date)" | tee -a "$LOG_FILE"
echo "Log file: $LOG_FILE"