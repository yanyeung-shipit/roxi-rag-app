#!/bin/bash

# fast_batch_processor.sh
# Process a batch of chunks very quickly with minimal overhead
# Designed for Replit environment to avoid timeouts

# Usage: ./fast_batch_processor.sh [CHUNK_COUNT]

# Configuration
CHUNK_COUNT=${1:-5}  # Number of chunks to process (default: 5)
TIMEOUT=30           # Timeout in seconds per chunk

echo "=============================================="
echo "FAST BATCH PROCESSOR"
echo "=============================================="
echo "Starting at: $(date)"
echo "Target: $CHUNK_COUNT chunks"
echo "=============================================="

# Get initial vector store size
INITIAL_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
echo "Initial vector store size: $INITIAL_COUNT chunks"

# Find unprocessed chunks
echo "Finding $CHUNK_COUNT unprocessed chunks..."
CHUNK_FILE="fast_batch_chunks.json"
python find_unprocessed_chunks.py --limit $CHUNK_COUNT --output $CHUNK_FILE

if [ ! -f "$CHUNK_FILE" ]; then
    echo "Error: Failed to generate list of unprocessed chunks"
    exit 1
fi

# Parse chunks into array
CHUNK_IDS=$(cat $CHUNK_FILE | tr -d '[]')
if [ -z "$CHUNK_IDS" ]; then
    echo "No unprocessed chunks found!"
    rm -f $CHUNK_FILE
    exit 0
fi

IFS=',' read -ra CHUNKS <<< "$CHUNK_IDS"
echo "Found ${#CHUNKS[@]} chunks to process"

# Make the direct processor executable
chmod +x direct_process_chunk.py

# Process each chunk sequentially
SUCCESSFUL=0
FAILED=0

for ((i=0; i<${#CHUNKS[@]}; i++)); do
    CHUNK_ID=${CHUNKS[$i]}
    CHUNK_ID=$(echo $CHUNK_ID | tr -d ' ')  # Remove any whitespace
    
    echo ""
    echo "=============================================="
    echo "PROCESSING CHUNK $((i+1)) OF ${#CHUNKS[@]} (ID: $CHUNK_ID)"
    echo "=============================================="
    
    # Process with timeout
    timeout $TIMEOUT python direct_process_chunk.py $CHUNK_ID
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
    
    # Check progress
    CURRENT_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
    PROGRESS=$(python check_progress.py | grep "Progress:" -A 1 | tail -n 1 | awk '{print $2}')
    
    echo "Progress: $PROGRESS ($CURRENT_COUNT chunks)"
    
    # Pause briefly between chunks
    if [ $i -lt $((${#CHUNKS[@]}-1)) ]; then
        echo "Pausing for 1 second before next chunk..."
        sleep 1
    fi
done

# Clean up
rm -f $CHUNK_FILE

# Final report
FINAL_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
ADDED=$((FINAL_COUNT - INITIAL_COUNT))

echo ""
echo "=============================================="
echo "BATCH PROCESSING COMPLETE"
echo "=============================================="
echo "Initial count:    $INITIAL_COUNT chunks"
echo "Final count:      $FINAL_COUNT chunks"
echo "Chunks added:     $ADDED of ${#CHUNKS[@]}"
echo "Success rate:     $SUCCESSFUL/${#CHUNKS[@]} ($(( (SUCCESSFUL*100)/${#CHUNKS[@]} ))%)"
echo "Progress:         $((FINAL_COUNT*100/1261))% of all chunks"
echo "Completed at:     $(date)"
echo "=============================================="