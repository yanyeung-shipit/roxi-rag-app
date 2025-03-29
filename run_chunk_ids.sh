#!/bin/bash

# run_chunk_ids.sh
# Process specific chunk IDs directly
# Usage: ./run_chunk_ids.sh CHUNK_ID [CHUNK_ID2 CHUNK_ID3 ...]

# Configuration
TIMEOUT=30               # Timeout per chunk in seconds
PAUSE=1                  # Pause between chunks in seconds

echo "=============================================="
echo "DIRECT CHUNK ID PROCESSOR"
echo "=============================================="
echo "Starting at:         $(date)"
echo "Chunk IDs:           $@"
echo "Timeout per chunk:   $TIMEOUT seconds"
echo "=============================================="

# Check if any chunk IDs were provided
if [ $# -eq 0 ]; then
    echo "Error: No chunk IDs provided. Usage: $0 CHUNK_ID [CHUNK_ID2 CHUNK_ID3 ...]"
    exit 1
fi

# Make scripts executable
chmod +x process_chunk.py

# Get initial vector store size
INITIAL_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
echo "Initial vector store size: $INITIAL_COUNT chunks"

# Initialize counters
SUCCESSFUL=0
FAILED=0
TOTAL_COUNT=$#

# Process each chunk ID provided as arguments
for CHUNK_ID in "$@"; do
    echo ""
    echo "Processing chunk $CHUNK_ID ($(( SUCCESSFUL + FAILED + 1 ))/$TOTAL_COUNT)"
    
    # Run with timeout
    timeout $TIMEOUT python process_chunk.py $CHUNK_ID
    RESULT=$?
    
    # Check result
    if [ $RESULT -eq 0 ]; then
        echo "✅ Successfully processed chunk $CHUNK_ID"
        SUCCESSFUL=$((SUCCESSFUL+1))
    elif [ $RESULT -eq 124 ]; then
        echo "⚠️ Chunk $CHUNK_ID processing timed out"
        FAILED=$((FAILED+1))
    else
        echo "❌ Failed to process chunk $CHUNK_ID (error $RESULT)"
        FAILED=$((FAILED+1))
    fi
    
    # Pause between chunks
    if [ $(( SUCCESSFUL + FAILED )) -lt $TOTAL_COUNT ]; then
        sleep $PAUSE
    fi
done

# Final report
FINAL_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
ADDED=$((FINAL_COUNT - INITIAL_COUNT))

echo ""
echo "=============================================="
echo "CHUNK PROCESSING COMPLETE"
echo "=============================================="
echo "Initial count:       $INITIAL_COUNT chunks"
echo "Final count:         $FINAL_COUNT chunks"
echo "Chunks added:        $ADDED chunks"
echo "Success rate:        $SUCCESSFUL/$TOTAL_COUNT chunks ($((SUCCESSFUL*100/TOTAL_COUNT))%)"
echo "Completed at:        $(date)"
echo "=============================================="

# Run final check_progress
python check_progress.py