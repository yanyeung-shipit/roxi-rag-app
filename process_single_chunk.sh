#!/bin/bash
# Process just a single chunk quickly to avoid timeouts
# This script takes the chunk ID to process

# Configuration
CHUNK_ID=${1}
LOG_FILE="logs/batch_processing/chunk_$(date +%Y%m%d_%H%M%S)_${CHUNK_ID}.log"

# Create log directory if it doesn't exist
mkdir -p "logs/batch_processing"

# Log the start
echo "======================================================" | tee -a "$LOG_FILE"
echo "SINGLE CHUNK PROCESSING START: $(date +%Y%m%d_%H%M%S)" | tee -a "$LOG_FILE"
echo "Chunk ID: $CHUNK_ID" | tee -a "$LOG_FILE"
echo "======================================================" | tee -a "$LOG_FILE"

# Check initial state
echo "Initial state:" | tee -a "$LOG_FILE"
python check_progress.py | grep "Vector store:" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Process the chunk
echo "Processing chunk $CHUNK_ID..." | tee -a "$LOG_FILE"
python direct_process_chunk.py $CHUNK_ID | tee -a "$LOG_FILE"

# Check final state
echo "" | tee -a "$LOG_FILE"
echo "Final state:" | tee -a "$LOG_FILE"
python check_progress.py | grep "Vector store:" | tee -a "$LOG_FILE"

echo "Chunk processing completed at $(date)" | tee -a "$LOG_FILE"
echo "Log file: $LOG_FILE"

# Echo success or failure
SUCCESS=$(tail -n 20 "$LOG_FILE" | grep -c "Processed chunk $CHUNK_ID")
if [ $SUCCESS -gt 0 ]; then
    echo "SUCCESS: Processed chunk $CHUNK_ID"
    exit 0
else
    echo "FAILURE: Failed to process chunk $CHUNK_ID"
    exit 1
fi