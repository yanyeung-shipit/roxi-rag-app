#!/bin/bash

# run_parallel_rebuild.sh
# This script runs the parallel chunk processor with automatic retries and restarts
# Usage: ./run_parallel_rebuild.sh [total_chunks] [batch_size]

# Configuration
TOTAL_CHUNKS=${1:-100}       # Total chunks to process (default: 100)
BATCH_SIZE=${2:-10}          # Batch size per run (default: 10)
MAX_RETRIES=10               # Maximum number of retries
RUN_TIMEOUT=300              # Timeout for each run (5 minutes)
COOLDOWN=10                  # Cooldown period between runs

echo "=============================================="
echo "PARALLEL VECTOR STORE REBUILD"
echo "=============================================="
echo "Starting at:         $(date)"
echo "Target chunks:       $TOTAL_CHUNKS"
echo "Batch size:          $BATCH_SIZE"
echo "Timeout per run:     $RUN_TIMEOUT seconds"
echo "=============================================="

# Initialize tracking
PROCESSED_SO_FAR=0
RETRY_COUNT=0
SUCCESSFUL_RUNS=0
FAILED_RUNS=0

# Main processing loop
while [ $PROCESSED_SO_FAR -lt $TOTAL_CHUNKS ] && [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    echo ""
    echo "=============================================="
    echo "STARTING RUN $((SUCCESSFUL_RUNS + FAILED_RUNS + 1))"
    echo "Already processed: $PROCESSED_SO_FAR chunks"
    echo "Target: $TOTAL_CHUNKS chunks"
    echo "=============================================="
    
    # Get current progress
    CURRENT_CHUNKS=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
    if [ -z "$CURRENT_CHUNKS" ]; then
        echo "Could not determine current progress, using last known value: $PROCESSED_SO_FAR"
    else
        PROCESSED_SO_FAR=$CURRENT_CHUNKS
        echo "Current progress: $PROCESSED_SO_FAR chunks in vector store"
    fi
    
    # Calculate remaining chunks for this run
    REMAINING=$((TOTAL_CHUNKS - PROCESSED_SO_FAR))
    if [ $REMAINING -le 0 ]; then
        echo "Target reached! $PROCESSED_SO_FAR/$TOTAL_CHUNKS chunks processed."
        break
    fi
    
    # Calculate chunks to process in this run
    CHUNKS_THIS_RUN=$BATCH_SIZE
    if [ $REMAINING -lt $BATCH_SIZE ]; then
        CHUNKS_THIS_RUN=$REMAINING
    fi
    
    echo "Processing $CHUNKS_THIS_RUN chunks in this run..."
    
    # Run the processor with a timeout
    timeout $RUN_TIMEOUT python parallel_chunk_processor.py --batch-size 5 --max-chunks $CHUNKS_THIS_RUN
    RESULT=$?
    
    # Check the result
    if [ $RESULT -eq 0 ]; then
        echo "✅ Run completed successfully!"
        SUCCESSFUL_RUNS=$((SUCCESSFUL_RUNS + 1))
        RETRY_COUNT=0  # Reset retry counter on success
    elif [ $RESULT -eq 124 ]; then
        echo "⚠️ Run timed out, but progress was likely made."
        RETRY_COUNT=$((RETRY_COUNT + 1))
        SUCCESSFUL_RUNS=$((SUCCESSFUL_RUNS + 1))  # Count as success since progress is checkpointed
    else
        echo "❌ Run failed with error code $RESULT."
        FAILED_RUNS=$((FAILED_RUNS + 1))
        RETRY_COUNT=$((RETRY_COUNT + 1))
    fi
    
    # Get updated progress
    NEW_CHUNKS=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
    if [ -n "$NEW_CHUNKS" ] && [ "$NEW_CHUNKS" != "$PROCESSED_SO_FAR" ]; then
        CHUNKS_ADDED=$((NEW_CHUNKS - PROCESSED_SO_FAR))
        PROCESSED_SO_FAR=$NEW_CHUNKS
        echo "Added $CHUNKS_ADDED new chunks in this run!"
        echo "Total progress: $PROCESSED_SO_FAR/$TOTAL_CHUNKS chunks ($((PROCESSED_SO_FAR * 100 / TOTAL_CHUNKS))%)"
    elif [ -n "$NEW_CHUNKS" ]; then
        echo "No new chunks were added in this run."
    fi
    
    # Cooldown period to let the system recover
    echo "Cooling down for $COOLDOWN seconds before next run..."
    sleep $COOLDOWN
done

# Final report
echo ""
echo "=============================================="
echo "REBUILD PROCESS COMPLETE"
echo "=============================================="
echo "Final status:        $PROCESSED_SO_FAR/$TOTAL_CHUNKS chunks"
echo "Progress:            $((PROCESSED_SO_FAR * 100 / TOTAL_CHUNKS))%"
echo "Successful runs:     $SUCCESSFUL_RUNS"
echo "Failed runs:         $FAILED_RUNS"
echo "Completed at:        $(date)"
echo "=============================================="

# Run full check_progress for final status
python check_progress.py