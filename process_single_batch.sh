#!/bin/bash

# process_single_batch.sh
# This script processes a single batch of chunks for the vector store rebuild process
# It's designed to be called repeatedly from other scripts or manually

# Default values if not provided
BATCH_SIZE=${1:-3}
DELAY_SECONDS=${2:-5}

echo "Starting single batch processing at $(date)"
echo "Configuration: BATCH_SIZE=$BATCH_SIZE, DELAY_SECONDS=$DELAY_SECONDS"
echo "-----------------------------------------"

# Check current progress
python check_progress.py

echo "-----------------------------------------"
echo "Batch started at $(date)"

# Process a single batch
for ((i=1; i<=$BATCH_SIZE; i++)); do
    echo "Processing chunk $i of $BATCH_SIZE in batch..."
    python add_single_chunk.py
    
    # Only sleep if there are more chunks to process in this batch
    if [ $i -lt $BATCH_SIZE ]; then
        echo "Sleeping for $DELAY_SECONDS seconds..."
        sleep $DELAY_SECONDS
    fi
done

echo "Batch completed at $(date)"
echo "-----------------------------------------"

# Check progress again after batch
python check_progress.py

echo "-----------------------------------------"
echo "Single batch processing completed."