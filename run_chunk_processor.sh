#!/bin/bash

# run_chunk_processor.sh
# Process a specific number of chunks sequentially
# This script is designed for maximum reliability in the Replit environment

# Usage: ./run_chunk_processor.sh [COUNT]

# Configuration
COUNT=${1:-5}        # Number of chunks to process (default: 5)

echo "=============================================="
echo "SEQUENTIAL CHUNK PROCESSOR"
echo "=============================================="
echo "Starting at: $(date)"
echo "Target: Process $COUNT chunks"
echo "=============================================="

# Get initial vector store size
INITIAL_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
echo "Initial vector store size: $INITIAL_COUNT chunks"

# Make other scripts executable
chmod +x process_single_chunk.sh direct_process_chunk.py

# Process chunks one by one
for ((i=1; i<=$COUNT; i++)); do
    echo ""
    echo "=============================================="
    echo "PROCESSING CHUNK $i OF $COUNT"
    echo "=============================================="
    
    # Process this chunk
    ./process_single_chunk.sh
    
    # Check current status
    CURRENT_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
    
    echo "Chunks processed: $i of $COUNT"
    echo "Current vector store size: $CURRENT_COUNT chunks"
    
    # Break if we've reached the end
    if [ $i -lt $COUNT ]; then
        echo "Continuing to next chunk..."
        sleep 1
    fi
done

# Final report
FINAL_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
ADDED=$((FINAL_COUNT - INITIAL_COUNT))
PROGRESS=$(python check_progress.py | grep "Progress:" -A 1 | tail -n 1 | awk '{print $2}')

echo ""
echo "=============================================="
echo "PROCESSING COMPLETE"
echo "=============================================="
echo "Initial count:    $INITIAL_COUNT chunks"
echo "Final count:      $FINAL_COUNT chunks"
echo "Chunks added:     $ADDED of $COUNT"
echo "Success rate:     $(( (ADDED*100)/COUNT ))%"
echo "Overall progress: $PROGRESS"
echo "Completed at:     $(date)"
echo "=============================================="