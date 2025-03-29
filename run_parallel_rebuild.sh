#!/bin/bash

# run_parallel_rebuild.sh
# Process multiple chunks in parallel to efficiently rebuild the vector store
# This script runs multiple batches in sequence to process a larger number of chunks

# Configuration
CHUNKS_PER_BATCH=${1:-10}    # Number of chunks per batch (default: 10)
WORKERS=${2:-3}              # Number of parallel workers (default: 3)
BATCHES=${3:-5}              # Number of batches to process (default: 5)
PAUSE_SECONDS=5              # Seconds to pause between batches

echo "=============================================="
echo "PARALLEL VECTOR STORE REBUILD"
echo "=============================================="
echo "Starting at: $(date)"
echo "Configuration:"
echo "  - $CHUNKS_PER_BATCH chunks per batch"
echo "  - $WORKERS parallel workers"
echo "  - $BATCHES total batches"
echo "  - Total chunks to process: $((CHUNKS_PER_BATCH * BATCHES))"
echo "=============================================="

# Make scripts executable
chmod +x parallel_chunk_processor.py find_unprocessed_chunks.py

# Get initial vector store size
INITIAL_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
echo "Initial vector store size: $INITIAL_COUNT chunks"

# Process batches
SUCCESSFUL=0
FAILED=0
TOTAL_TIME=0

for ((batch=1; batch<=BATCHES; batch++)); do
    echo ""
    echo "=============================================="
    echo "PROCESSING BATCH $batch OF $BATCHES"
    echo "=============================================="
    
    # Find unprocessed chunks and save to file
    echo "Finding next $CHUNKS_PER_BATCH unprocessed chunks..."
    CHUNK_FILE="batch_${batch}_chunks.json"
    python find_unprocessed_chunks.py --limit $CHUNKS_PER_BATCH --output $CHUNK_FILE
    
    if [ ! -f "$CHUNK_FILE" ]; then
        echo "Error: Failed to generate list of unprocessed chunks"
        exit 1
    fi
    
    # Check if we have any chunks to process
    CHUNK_IDS=$(cat $CHUNK_FILE | tr -d '[]')
    if [ -z "$CHUNK_IDS" ]; then
        echo "No more unprocessed chunks found! Finishing early."
        rm -f $CHUNK_FILE
        break
    fi
    
    # Count chunks in this batch
    IFS=',' read -ra CHUNKS_ARRAY <<< "$CHUNK_IDS"
    echo "Found ${#CHUNKS_ARRAY[@]} chunks to process in this batch"
    
    # Process this batch
    echo "Starting batch processing with $WORKERS workers..."
    BATCH_START=$(date +%s)
    python parallel_chunk_processor.py --input $CHUNK_FILE --workers $WORKERS
    RESULT=$?
    BATCH_END=$(date +%s)
    BATCH_TIME=$((BATCH_END - BATCH_START))
    TOTAL_TIME=$((TOTAL_TIME + BATCH_TIME))
    
    # Get batch results
    CURRENT_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
    BATCH_ADDED=$((CURRENT_COUNT - INITIAL_COUNT - SUCCESSFUL))
    SUCCESSFUL=$((SUCCESSFUL + BATCH_ADDED))
    
    echo "Batch $batch complete:"
    echo "  - Processed ${#CHUNKS_ARRAY[@]} chunks"
    echo "  - Added $BATCH_ADDED chunks to vector store"
    echo "  - Time taken: $BATCH_TIME seconds"
    echo "  - Current vector store size: $CURRENT_COUNT chunks"
    
    # Clean up
    rm -f $CHUNK_FILE
    
    # Get overall progress
    PROGRESS=$(python check_progress.py | grep "Progress:" -A 1 | tail -n 1 | awk '{print $2}')
    echo "Overall progress: $PROGRESS"
    
    # Pause between batches
    if [ $batch -lt $BATCHES ]; then
        echo "Pausing for $PAUSE_SECONDS seconds before next batch..."
        sleep $PAUSE_SECONDS
    fi
done

# Final report
FINAL_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
ADDED=$((FINAL_COUNT - INITIAL_COUNT))
PROGRESS=$(python check_progress.py | grep "Progress:" -A 1 | tail -n 1 | awk '{print $2}')

echo ""
echo "=============================================="
echo "PARALLEL PROCESSING COMPLETE"
echo "=============================================="
echo "Initial count:    $INITIAL_COUNT chunks"
echo "Final count:      $FINAL_COUNT chunks"
echo "Chunks added:     $ADDED"
echo "Success rate:     $SUCCESSFUL/$((CHUNKS_PER_BATCH * BATCHES)) ($(( (SUCCESSFUL*100)/(CHUNKS_PER_BATCH * BATCHES < 1 ? 1 : CHUNKS_PER_BATCH * BATCHES) ))%)"
echo "Total time:       $TOTAL_TIME seconds"
echo "Progress:         $PROGRESS"
echo "Completed at:     $(date)"
echo "=============================================="