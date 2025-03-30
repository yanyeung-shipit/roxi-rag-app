#!/bin/bash

# run_rebuild_batches.sh
# Run multiple batch processing sessions with reporting
# Usage: ./run_rebuild_batches.sh [BATCH_COUNT] [CHUNKS_PER_BATCH]

# Configuration
BATCH_COUNT=${1:-10}        # Number of batches to run (default: 10)
CHUNKS_PER_BATCH=${2:-5}    # Number of chunks per batch (default: 5)
PAUSE_BETWEEN=5             # Pause between batches in seconds

echo "=============================================="
echo "BATCH REBUILD CONTROLLER"
echo "=============================================="
echo "Starting at:         $(date)"
echo "Batch count:         $BATCH_COUNT"
echo "Chunks per batch:    $CHUNKS_PER_BATCH"
echo "Total target chunks: $((BATCH_COUNT * CHUNKS_PER_BATCH))"
echo "=============================================="

# Make script executable
chmod +x process_multiple_chunks.sh

# Get initial vector store size
INITIAL_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
echo "Initial vector store size: $INITIAL_COUNT chunks"

# Run batches
for ((batch=1; batch<=BATCH_COUNT; batch++)); do
    echo ""
    echo "=============================================="
    echo "RUNNING BATCH $batch of $BATCH_COUNT"
    echo "=============================================="
    
    # Run the batch processor
    ./process_multiple_chunks.sh $CHUNKS_PER_BATCH
    
    # Wait between batches (except for the last one)
    if [ $batch -lt $BATCH_COUNT ]; then
        echo "Pausing for $PAUSE_BETWEEN seconds before next batch..."
        sleep $PAUSE_BETWEEN
    fi
done

# Final report
FINAL_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
ADDED=$((FINAL_COUNT - INITIAL_COUNT))
TARGET=$((BATCH_COUNT * CHUNKS_PER_BATCH))

echo ""
echo "=============================================="
echo "ALL BATCHES COMPLETE"
echo "=============================================="
echo "Started with:        $INITIAL_COUNT chunks"
echo "Finished with:       $FINAL_COUNT chunks"
echo "Total chunks added:  $ADDED of $TARGET planned chunks"
echo "Success rate:        $((ADDED*100/TARGET))%"
echo "New progress:        $((FINAL_COUNT*100/1261))% of all chunks"
echo "Completed at:        $(date)"
echo "=============================================="