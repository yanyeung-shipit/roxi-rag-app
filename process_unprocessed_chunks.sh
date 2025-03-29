#!/bin/bash

# process_unprocessed_chunks.sh
# Find unprocessed chunks and process them in batches
# Usage: ./process_unprocessed_chunks.sh [BATCH_COUNT] [CHUNKS_PER_BATCH]

# Configuration
BATCH_COUNT=${1:-5}        # Number of batches to run (default: 5)
CHUNKS_PER_BATCH=${2:-10}  # Number of chunks per batch (default: 10)
UNPROCESSED_FILE="unprocessed_chunks.json"
PAUSE_BETWEEN=2            # Pause between batches in seconds

echo "=============================================="
echo "UNPROCESSED CHUNKS PROCESSOR"
echo "=============================================="
echo "Starting at:         $(date)"
echo "Batch count:         $BATCH_COUNT"
echo "Chunks per batch:    $CHUNKS_PER_BATCH"
echo "Total chunks target: $((BATCH_COUNT * CHUNKS_PER_BATCH))"
echo "=============================================="

# Make scripts executable
chmod +x find_unprocessed_chunks.py fast_process_chunk.py

# Find all unprocessed chunks
echo "Finding unprocessed chunks..."
python find_unprocessed_chunks.py --output $UNPROCESSED_FILE

if [ ! -f "$UNPROCESSED_FILE" ]; then
    echo "Error: Failed to generate list of unprocessed chunks"
    exit 1
fi

# Get the count of unprocessed chunks
TOTAL_UNPROCESSED=$(cat $UNPROCESSED_FILE | tr -d '[]' | tr ',' '\n' | wc -l)
echo "Found $TOTAL_UNPROCESSED unprocessed chunks"

# Limit to our target
TARGET_CHUNKS=$((BATCH_COUNT * CHUNKS_PER_BATCH))
CHUNKS_TO_PROCESS=$((TOTAL_UNPROCESSED < TARGET_CHUNKS ? TOTAL_UNPROCESSED : TARGET_CHUNKS))
echo "Will process up to $CHUNKS_TO_PROCESS chunks"

# Get initial vector store size
INITIAL_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
echo "Initial vector store size: $INITIAL_COUNT chunks"

# Parse the unprocessed chunks list into an array
IFS=',' read -ra CHUNK_IDS <<< "$(cat $UNPROCESSED_FILE | tr -d '[]')"

# Track overall success/failure
SUCCESSFUL=0
FAILED=0
PROCESSED=0

# Process chunks in batches
for ((batch=1; batch<=BATCH_COUNT; batch++)); do
    echo ""
    echo "=============================================="
    echo "PROCESSING BATCH $batch of $BATCH_COUNT"
    echo "=============================================="
    
    # Calculate start and end indices for this batch
    START=$(( (batch-1) * CHUNKS_PER_BATCH ))
    END=$(( batch * CHUNKS_PER_BATCH - 1 ))
    
    # Make sure we don't exceed array bounds
    if [ $START -ge ${#CHUNK_IDS[@]} ]; then
        echo "No more chunks to process!"
        break
    fi
    
    if [ $END -ge ${#CHUNK_IDS[@]} ]; then
        END=$(( ${#CHUNK_IDS[@]} - 1 ))
    fi
    
    echo "Processing chunks $START to $END (indices)"
    
    # Process each chunk in this batch
    for ((i=START; i<=END; i++)); do
        if [ $i -ge ${#CHUNK_IDS[@]} ]; then
            break
        fi
        
        CHUNK_ID=${CHUNK_IDS[$i]}
        CHUNK_ID=$(echo $CHUNK_ID | tr -d ' ')  # Remove any whitespace
        
        if [ -z "$CHUNK_ID" ]; then
            continue  # Skip empty IDs
        fi
        
        echo ""
        echo "=============================================="
        echo "PROCESSING CHUNK $((i-START+1)) of $((END-START+1)) (ID: $CHUNK_ID)"
        echo "=============================================="
        
        # Process the chunk
        python fast_process_chunk.py $CHUNK_ID
        RESULT=$?
        
        # Check result
        if [ $RESULT -eq 0 ]; then
            echo "✅ Successfully processed chunk $CHUNK_ID"
            SUCCESSFUL=$((SUCCESSFUL+1))
        else
            echo "❌ Failed to process chunk $CHUNK_ID with error $RESULT"
            FAILED=$((FAILED+1))
        fi
        
        PROCESSED=$((PROCESSED+1))
        
        # Check current progress
        CURRENT_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
        PROGRESS=$(python check_progress.py | grep "Progress:" -A 1 | tail -n 1 | awk '{print $2}')
        
        echo ""
        echo "--- Progress Update ---"
        echo "Processed in batch: $((i-START+1))/$((END-START+1))"
        echo "Total processed:    $PROCESSED/$CHUNKS_TO_PROCESS"
        echo "Successful:         $SUCCESSFUL chunks"
        echo "Failed:             $FAILED chunks"
        echo "Current count:      $CURRENT_COUNT chunks"
        echo "Progress:           $PROGRESS"
        echo "----------------------"
        
        # Pause between chunks
        if [ $i -lt $END ]; then
            echo "Pausing for 1 second before next chunk..."
            sleep 1
        fi
    done
    
    # Pause between batches
    if [ $batch -lt $BATCH_COUNT ] && [ $((batch * CHUNKS_PER_BATCH)) -lt ${#CHUNK_IDS[@]} ]; then
        echo "Pausing for $PAUSE_BETWEEN seconds before next batch..."
        sleep $PAUSE_BETWEEN
    fi
done

# Clean up
rm -f $UNPROCESSED_FILE

# Final report
FINAL_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
ADDED=$((FINAL_COUNT - INITIAL_COUNT))

echo ""
echo "=============================================="
echo "BATCH PROCESSING COMPLETE"
echo "=============================================="
echo "Initial count:      $INITIAL_COUNT chunks"
echo "Final count:        $FINAL_COUNT chunks"
echo "Chunks added:       $ADDED chunks"
echo "Chunks processed:   $PROCESSED chunks"
echo "Success rate:       $SUCCESSFUL/$PROCESSED chunks ($(( (SUCCESSFUL*100)/PROCESSED ))%)"
echo "Current progress:   $((FINAL_COUNT*100/1261))% of all chunks"
echo "Completed at:       $(date)"
echo "=============================================="