#!/bin/bash

# process_chunk_batch.sh
# Process a batch of chunks using direct chunk IDs
# Usage: ./process_chunk_batch.sh CHUNK_COUNT BATCH_SIZE

# Configuration
CHUNK_COUNT=${1:-10}     # Number of chunks to process (default: 10)
BATCH_SIZE=${2:-5}       # Number of chunks per batch (default: 5)
TIMEOUT=30               # Timeout per chunk in seconds
PAUSE=1                  # Pause between chunks in seconds
BATCH_PAUSE=5            # Pause between batches in seconds
CHUNK_LIST_FILE="chunks_to_process.json"

echo "=============================================="
echo "DIRECT CHUNK BATCH PROCESSOR"
echo "=============================================="
echo "Starting at:         $(date)"
echo "Target chunks:       $CHUNK_COUNT"
echo "Batch size:          $BATCH_SIZE"
echo "Timeout per chunk:   $TIMEOUT seconds"
echo "=============================================="

# Make scripts executable
chmod +x process_chunk.py find_unprocessed_chunks.py

# Get initial vector store size
INITIAL_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
echo "Initial vector store size: $INITIAL_COUNT chunks"

# Get list of unprocessed chunks
echo "Finding unprocessed chunks..."
python find_unprocessed_chunks.py --limit $CHUNK_COUNT --output $CHUNK_LIST_FILE

# Verify we got chunk IDs
if [ ! -f "$CHUNK_LIST_FILE" ]; then
    echo "Error: Failed to generate list of unprocessed chunks"
    exit 1
fi

# Load chunk IDs
CHUNKS=$(cat $CHUNK_LIST_FILE)
CHUNKS=$(echo $CHUNKS | tr -d '[]')  # Remove brackets
CHUNKS=$(echo $CHUNKS | tr ',' ' ')  # Replace commas with spaces

# Convert to array
CHUNK_ARRAY=($CHUNKS)
ACTUAL_COUNT=${#CHUNK_ARRAY[@]}

echo "Found $ACTUAL_COUNT chunks to process"

# Check if we have any chunks to process
if [ $ACTUAL_COUNT -eq 0 ]; then
    echo "No chunks to process!"
    exit 0
fi

# Calculate number of batches
TOTAL_BATCHES=$(( (ACTUAL_COUNT + BATCH_SIZE - 1) / BATCH_SIZE ))

# Initialize counters
SUCCESSFUL=0
FAILED=0

# Process in batches
for ((batch=1; batch<=TOTAL_BATCHES; batch++)); do
    echo ""
    echo "=============================================="
    echo "BATCH $batch of $TOTAL_BATCHES"
    echo "=============================================="
    
    # Calculate start and end indices for this batch
    START_IDX=$(( (batch-1) * BATCH_SIZE ))
    END_IDX=$(( batch * BATCH_SIZE - 1 ))
    
    # Ensure end index doesn't exceed array size
    if [ $END_IDX -ge $ACTUAL_COUNT ]; then
        END_IDX=$(( ACTUAL_COUNT - 1 ))
    fi
    
    BATCH_SUCCESSFUL=0
    BATCH_FAILED=0
    
    # Process each chunk in the batch
    for ((i=START_IDX; i<=END_IDX; i++)); do
        CHUNK_ID=${CHUNK_ARRAY[$i]}
        
        echo ""
        echo "Processing chunk $CHUNK_ID ($(( i - START_IDX + 1 ))/$((END_IDX - START_IDX + 1)) in batch)"
        
        # Run with timeout
        timeout $TIMEOUT python process_chunk.py $CHUNK_ID
        RESULT=$?
        
        # Check result
        if [ $RESULT -eq 0 ]; then
            echo "✅ Successfully processed chunk $CHUNK_ID"
            SUCCESSFUL=$((SUCCESSFUL+1))
            BATCH_SUCCESSFUL=$((BATCH_SUCCESSFUL+1))
        elif [ $RESULT -eq 124 ]; then
            echo "⚠️ Chunk $CHUNK_ID processing timed out"
            FAILED=$((FAILED+1))
            BATCH_FAILED=$((BATCH_FAILED+1))
        else
            echo "❌ Failed to process chunk $CHUNK_ID (error $RESULT)"
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
    echo "Successful:      $BATCH_SUCCESSFUL/$((END_IDX-START_IDX+1)) chunks"
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
echo "BATCH PROCESSING COMPLETE"
echo "=============================================="
echo "Initial count:       $INITIAL_COUNT chunks"
echo "Final count:         $FINAL_COUNT chunks"
echo "Chunks added:        $ADDED chunks"
echo "Success rate:        $SUCCESSFUL/$ACTUAL_COUNT chunks ($((SUCCESSFUL*100/ACTUAL_COUNT))%)"
echo "Completed at:        $(date)"
echo "=============================================="

# Clean up
rm -f $CHUNK_LIST_FILE

# Run final check_progress
python check_progress.py