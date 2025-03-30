#!/bin/bash

# Run the chunk processor with a target of 75% completion
# This script processes chunks until 75% of the documents are in the vector store
# Usage: ./run_to_75_percent.sh [batch_size] [delay_seconds]

# Default values
BATCH_SIZE=${1:-5}
DELAY_SECONDS=${2:-3}

echo "Starting chunk processor to reach 75% target..."
echo "Using batch size: $BATCH_SIZE with $DELAY_SECONDS seconds delay between batches"

# Run in the Flask app context
python run_chunk_processor.py --batch-size $BATCH_SIZE --target 75.0 --delay $DELAY_SECONDS