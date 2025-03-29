#!/bin/bash

# run_fast_rebuild.sh
# This script runs the fast chunk processor multiple times in succession
# Usage: ./run_fast_rebuild.sh [chunk_count] [batch_count]
#
# Example: ./run_fast_rebuild.sh 50 10
#          This will process 50 chunks total, running in batches of 10 at a time

# Configuration
CHUNK_COUNT=${1:-20}        # Number of chunks to process (default: 20)
BATCH_SIZE=${2:-5}          # Number of chunks per batch (default: 5)
TIMEOUT=30                  # Timeout per chunk in seconds
PAUSE=1                     # Pause between chunks in seconds
BATCH_PAUSE=5               # Pause between batches in seconds

echo "=============================================="
echo "FAST VECTOR STORE REBUILD"
echo "=============================================="
echo "Starting at:         $(date)"
echo "Target chunks:       $CHUNK_COUNT"
echo "Batch size:          $BATCH_SIZE"
echo "Timeout per chunk:   $TIMEOUT seconds"
echo "=============================================="

# Make the processor executable
chmod +x fast_chunk_processor.py

# Initialize counters
SUCCESSFUL=0
FAILED=0
INITIAL_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')

# Calculate number of batches needed
TOTAL_BATCHES=$(( (CHUNK_COUNT + BATCH_SIZE - 1) / BATCH_SIZE ))

# Process in batches
for ((batch=1; batch<=TOTAL_BATCHES; batch++)); do
    echo ""
    echo "=============================================="
    echo "BATCH $batch of $TOTAL_BATCHES"
    echo "=============================================="
    
    # Calculate start and end chunk numbers for this batch
    START_CHUNK=$(( (batch-1) * BATCH_SIZE + 1 ))
    END_CHUNK=$(( batch * BATCH_SIZE ))
    
    # Ensure end chunk doesn't exceed total count
    if [ $END_CHUNK -gt $CHUNK_COUNT ]; then
        END_CHUNK=$CHUNK_COUNT
    fi
    
    BATCH_SUCCESSFUL=0
    BATCH_FAILED=0
    
    # Process each chunk in the batch
    for ((i=START_CHUNK; i<=END_CHUNK; i++)); do
        echo ""
        echo "Processing chunk $i of $CHUNK_COUNT (Batch $batch/$TOTAL_BATCHES)"
        
        # Run with timeout
        timeout $TIMEOUT python fast_chunk_processor.py
        RESULT=$?
        
        # Check result
        if [ $RESULT -eq 0 ]; then
            echo "✅ Successfully processed chunk $i"
            SUCCESSFUL=$((SUCCESSFUL+1))
            BATCH_SUCCESSFUL=$((BATCH_SUCCESSFUL+1))
        elif [ $RESULT -eq 124 ]; then
            echo "⚠️ Chunk $i processing timed out"
            FAILED=$((FAILED+1))
            BATCH_FAILED=$((BATCH_FAILED+1))
        else
            echo "❌ Failed to process chunk $i (error $RESULT)"
            FAILED=$((FAILED+1))
            BATCH_FAILED=$((BATCH_FAILED+1))
        fi
        
        # Pause between chunks
        sleep $PAUSE
    done
    
    # Check progress after each batch
    CURRENT_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
    PROGRESS=$(python check_progress.py | grep "Progress:" -A 1 | tail -n 1 | awk '{print $2}')
    
    echo ""
    echo "--- Batch $batch/$TOTAL_BATCHES Summary ---"
    echo "Successful:      $BATCH_SUCCESSFUL/$((END_CHUNK-START_CHUNK+1)) chunks"
    echo "Current count:   $CURRENT_COUNT chunks"
    echo "Progress:        $PROGRESS"
    echo "---------------------------------"
    
    # Pause between batches
    if [ $batch -lt $TOTAL_BATCHES ]; then
        echo "Pausing for $BATCH_PAUSE seconds before next batch..."
        sleep $BATCH_PAUSE
    fi
done

# Final report
FINAL_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
ADDED=$((FINAL_COUNT - INITIAL_COUNT))

echo ""
echo "=============================================="
echo "FAST REBUILD PROCESS COMPLETE"
echo "=============================================="
echo "Initial count:       $INITIAL_COUNT chunks"
echo "Final count:         $FINAL_COUNT chunks"
echo "Chunks added:        $ADDED chunks"
echo "Success rate:        $SUCCESSFUL/$CHUNK_COUNT chunks ($((SUCCESSFUL*100/CHUNK_COUNT))%)"
echo "Completed at:        $(date)"
echo "=============================================="

# Run full check_progress for final status
python check_progress.py