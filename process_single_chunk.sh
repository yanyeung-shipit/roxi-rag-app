#!/bin/bash

# process_single_chunk.sh
# Process a single chunk with maximum reliability
# Usage: ./process_single_chunk.sh

# Configuration
TIMEOUT=25              # Timeout in seconds for chunk processing
MAX_RETRIES=3           # Maximum number of retries for a failed chunk
CHUNK_LIST_FILE="chunks_to_process.json"

echo "=============================================="
echo "SINGLE CHUNK PROCESSOR"
echo "=============================================="
echo "Starting at:        $(date)"
echo "Timeout:            $TIMEOUT seconds"
echo "Max retries:        $MAX_RETRIES"
echo "=============================================="

# Make scripts executable
chmod +x process_chunk.py find_unprocessed_chunks.py

# Get initial vector store size
INITIAL_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
echo "Initial vector store size: $INITIAL_COUNT chunks"

# Get the next unprocessed chunk ID
echo "Finding next unprocessed chunk..."
python find_unprocessed_chunks.py --limit 1 --output $CHUNK_LIST_FILE
if [ ! -f "$CHUNK_LIST_FILE" ]; then
    echo "Error: Failed to generate list of unprocessed chunks"
    exit 1
fi

# Get the chunk ID
CHUNK_ID=$(cat $CHUNK_LIST_FILE | tr -d '[]')
if [ -z "$CHUNK_ID" ]; then
    echo "No more chunks to process!"
    exit 0
fi

echo "Selected chunk ID: $CHUNK_ID"

# Try to process the chunk with retries
for ((i=1; i<=MAX_RETRIES; i++)); do
    echo ""
    echo "Processing attempt $i/$MAX_RETRIES for chunk $CHUNK_ID"
    
    # Run with timeout
    timeout $TIMEOUT python process_chunk.py $CHUNK_ID
    RESULT=$?
    
    # Check result
    if [ $RESULT -eq 0 ]; then
        echo "✅ Successfully processed chunk $CHUNK_ID"
        break
    elif [ $RESULT -eq 124 ]; then
        echo "⚠️ Chunk $CHUNK_ID processing timed out (attempt $i/$MAX_RETRIES)"
    else
        echo "❌ Failed to process chunk $CHUNK_ID with error $RESULT (attempt $i/$MAX_RETRIES)"
    fi
    
    # If this was the last retry, break
    if [ $i -eq $MAX_RETRIES ]; then
        echo "❌ Maximum retries reached for chunk $CHUNK_ID"
    fi
    
    # Pause briefly before retrying
    sleep 2
done

# Final report
FINAL_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
ADDED=$((FINAL_COUNT - INITIAL_COUNT))

echo ""
echo "=============================================="
echo "SINGLE CHUNK PROCESSING COMPLETE"
echo "=============================================="
echo "Initial count:      $INITIAL_COUNT chunks"
echo "Final count:        $FINAL_COUNT chunks"
echo "Chunks added:       $ADDED chunks"
if [ $ADDED -gt 0 ]; then
    echo "Result:            ✅ SUCCESS"
else
    echo "Result:            ❌ FAILED"
fi
echo "Completed at:       $(date)"
echo "=============================================="

# Clean up
rm -f $CHUNK_LIST_FILE