#!/bin/bash

# process_next_chunks.sh
# Process 5 unprocessed chunks at a time
# This version loads smaller batches incrementally to avoid timeout issues

# Configuration
CHUNK_COUNT=${1:-5}          # Number of chunks to process (default: 5)
TIMEOUT=20                   # Timeout in seconds for each chunk
CHUNK_LIST_FILE="next_chunks.json"

echo "=============================================="
echo "PROCESSING NEXT $CHUNK_COUNT CHUNKS"
echo "=============================================="
echo "Starting at: $(date)"
echo "=============================================="

# Make scripts executable
chmod +x find_unprocessed_chunks.py fast_process_chunk.py

# Find unprocessed chunks - limited to a small batch
echo "Finding next $CHUNK_COUNT unprocessed chunks..."
python find_unprocessed_chunks.py --limit $CHUNK_COUNT --output $CHUNK_LIST_FILE

if [ ! -f "$CHUNK_LIST_FILE" ]; then
    echo "Error: Failed to generate list of unprocessed chunks"
    exit 1
fi

# Get the list of chunks
CHUNK_IDS=$(cat $CHUNK_LIST_FILE | tr -d '[]')
if [ -z "$CHUNK_IDS" ]; then
    echo "No unprocessed chunks found!"
    rm -f $CHUNK_LIST_FILE
    exit 0
fi

# Count the chunks
CHUNK_COUNT=$(echo $CHUNK_IDS | tr ',' '\n' | wc -l)
echo "Found $CHUNK_COUNT chunks to process"

# Get initial vector store size
INITIAL_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
echo "Current vector store size: $INITIAL_COUNT chunks"

# Parse the comma-separated list into an array
IFS=',' read -ra CHUNKS <<< "$CHUNK_IDS"

# Track success/failure
SUCCESSFUL=0
FAILED=0

# Process each chunk
for ((i=0; i<${#CHUNKS[@]}; i++)); do
    CHUNK_ID=${CHUNKS[$i]}
    CHUNK_ID=$(echo $CHUNK_ID | tr -d ' ')  # Remove any whitespace
    
    echo ""
    echo "=============================================="
    echo "PROCESSING CHUNK $((i+1)) of ${#CHUNKS[@]} (ID: $CHUNK_ID)"
    echo "=============================================="
    
    # Process with timeout
    timeout $TIMEOUT python fast_process_chunk.py $CHUNK_ID
    RESULT=$?
    
    # Check result
    if [ $RESULT -eq 0 ]; then
        echo "✅ Successfully processed chunk $CHUNK_ID"
        SUCCESSFUL=$((SUCCESSFUL+1))
    elif [ $RESULT -eq 124 ]; then
        echo "⚠️ Chunk $CHUNK_ID processing timed out"
        FAILED=$((FAILED+1))
    else
        echo "❌ Failed to process chunk $CHUNK_ID with error $RESULT"
        FAILED=$((FAILED+1))
    fi
    
    # Pause briefly between chunks
    if [ $i -lt $((${#CHUNKS[@]}-1)) ]; then
        echo "Pausing for 1 second before next chunk..."
        sleep 1
    fi
done

# Clean up
rm -f $CHUNK_LIST_FILE

# Final report
FINAL_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
ADDED=$((FINAL_COUNT - INITIAL_COUNT))

echo ""
echo "=============================================="
echo "PROCESSING COMPLETE"
echo "=============================================="
echo "Initial count:    $INITIAL_COUNT chunks"
echo "Final count:      $FINAL_COUNT chunks"
echo "Chunks added:     $ADDED of ${#CHUNKS[@]}"
echo "Success rate:     $SUCCESSFUL/${#CHUNKS[@]} ($(( (SUCCESSFUL*100)/${#CHUNKS[@]} ))%)"
echo "Progress:         $((FINAL_COUNT*100/1261))% of all chunks"
echo "Completed at:     $(date)"
echo "=============================================="