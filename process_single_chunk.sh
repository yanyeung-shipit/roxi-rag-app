#!/bin/bash

# process_single_chunk.sh
# Process a single chunk with minimal overhead
# This script is designed for maximum reliability in the Replit environment

# Usage: ./process_single_chunk.sh [CHUNK_ID]

# Get a chunk ID to process
if [ $# -eq 1 ]; then
    # Use the provided chunk ID
    CHUNK_ID=$1
else
    # Find the next unprocessed chunk
    echo "Finding next unprocessed chunk..."
    CHUNK_FILE="single_chunk.json"
    python find_unprocessed_chunks.py --limit 1 --output $CHUNK_FILE
    
    if [ ! -f "$CHUNK_FILE" ]; then
        echo "Error: Failed to find an unprocessed chunk"
        exit 1
    fi
    
    CHUNK_ID=$(cat $CHUNK_FILE | tr -d '[]' | tr -d ' ')
    rm -f $CHUNK_FILE
    
    if [ -z "$CHUNK_ID" ]; then
        echo "No unprocessed chunks found!"
        exit 0
    fi
fi

echo "=============================================="
echo "PROCESSING CHUNK ID: $CHUNK_ID"
echo "=============================================="
echo "Starting at: $(date)"
echo "=============================================="

# Make the direct processor executable
chmod +x direct_process_chunk.py

# Process the chunk
python direct_process_chunk.py $CHUNK_ID
RESULT=$?

# Check result
if [ $RESULT -eq 0 ]; then
    echo "✅ Successfully processed chunk $CHUNK_ID"
else
    echo "❌ Failed to process chunk $CHUNK_ID with error $RESULT"
fi

# Check progress
python check_progress.py

echo "Completed at: $(date)"
echo "=============================================="