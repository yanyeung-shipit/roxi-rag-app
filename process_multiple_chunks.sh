#!/bin/bash

# process_multiple_chunks.sh
# Process multiple chunks one by one with high reliability
# Usage: ./process_multiple_chunks.sh [COUNT]

# Configuration
COUNT=${1:-5}            # Number of chunks to process (default: 5)
TIMEOUT=25              # Timeout in seconds for chunk processing
MAX_RETRIES=3           # Maximum number of retries for a failed chunk
PAUSE_BETWEEN=5         # Pause between chunks in seconds
CHUNK_LIST_FILE="chunks_to_process.json"

echo "=============================================="
echo "SEQUENTIAL MULTI-CHUNK PROCESSOR"
echo "=============================================="
echo "Starting at:        $(date)"
echo "Target chunks:      $COUNT"
echo "Timeout:            $TIMEOUT seconds"
echo "Max retries:        $MAX_RETRIES"
echo "=============================================="

# Make scripts executable
chmod +x process_chunk.py find_unprocessed_chunks.py

# Get initial vector store size
INITIAL_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
echo "Initial vector store size: $INITIAL_COUNT chunks"

# Track overall success/failure
SUCCESSFUL=0
FAILED=0

# Process each chunk
for ((chunk=1; chunk<=COUNT; chunk++)); do
    echo ""
    echo "=============================================="
    echo "PROCESSING CHUNK $chunk of $COUNT"
    echo "=============================================="
    
    # Get the next unprocessed chunk ID
    echo "Finding next unprocessed chunk..."
    python find_unprocessed_chunks.py --limit 1 --output $CHUNK_LIST_FILE
    if [ ! -f "$CHUNK_LIST_FILE" ]; then
        echo "Error: Failed to generate list of unprocessed chunks"
        break
    fi
    
    # Get the chunk ID
    CHUNK_ID=$(cat $CHUNK_LIST_FILE | tr -d '[]')
    if [ -z "$CHUNK_ID" ]; then
        echo "No more chunks to process!"
        break
    fi
    
    echo "Selected chunk ID: $CHUNK_ID"
    
    # Try to process the chunk with retries
    CHUNK_SUCCESS=false
    for ((i=1; i<=MAX_RETRIES; i++)); do
        echo ""
        echo "Processing attempt $i/$MAX_RETRIES for chunk $CHUNK_ID"
        
        # Run with timeout
        timeout $TIMEOUT python process_chunk.py $CHUNK_ID
        RESULT=$?
        
        # Check result
        if [ $RESULT -eq 0 ]; then
            echo "✅ Successfully processed chunk $CHUNK_ID"
            CHUNK_SUCCESS=true
            SUCCESSFUL=$((SUCCESSFUL+1))
            break
        elif [ $RESULT -eq 124 ]; then
            echo "⚠️ Chunk $CHUNK_ID processing timed out (attempt $i/$MAX_RETRIES)"
        else
            echo "❌ Failed to process chunk $CHUNK_ID with error $RESULT (attempt $i/$MAX_RETRIES)"
        fi
        
        # If this was the last retry, record as failed
        if [ $i -eq $MAX_RETRIES ] && [ "$CHUNK_SUCCESS" = false ]; then
            echo "❌ Maximum retries reached for chunk $CHUNK_ID"
            FAILED=$((FAILED+1))
        fi
        
        # Pause briefly before retrying
        if [ $i -lt $MAX_RETRIES ]; then
            sleep 2
        fi
    done
    
    # Clean up chunk list file
    rm -f $CHUNK_LIST_FILE
    
    # Check current progress
    CURRENT_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
    PROGRESS=$(python check_progress.py | grep "Progress:" -A 1 | tail -n 1 | awk '{print $2}')
    
    echo ""
    echo "--- Progress Update ---"
    echo "Processed chunks:  $chunk/$COUNT"
    echo "Successful:        $SUCCESSFUL chunks"
    echo "Failed:            $FAILED chunks"
    echo "Current count:     $CURRENT_COUNT chunks"
    echo "Progress:          $PROGRESS"
    echo "----------------------"
    
    # Pause between chunks
    if [ $chunk -lt $COUNT ]; then
        echo "Pausing for $PAUSE_BETWEEN seconds before next chunk..."
        sleep $PAUSE_BETWEEN
    fi
done

# Final report
FINAL_COUNT=$(python check_progress.py | grep "Vector store:" | awk '{print $3}')
ADDED=$((FINAL_COUNT - INITIAL_COUNT))
ACTUAL_COUNT=$((SUCCESSFUL + FAILED))

echo ""
echo "=============================================="
echo "BATCH PROCESSING COMPLETE"
echo "=============================================="
echo "Initial count:      $INITIAL_COUNT chunks"
echo "Final count:        $FINAL_COUNT chunks"
echo "Chunks added:       $ADDED chunks"
echo "Chunks attempted:   $ACTUAL_COUNT chunks"
echo "Success rate:       $SUCCESSFUL/$ACTUAL_COUNT chunks ($(( (SUCCESSFUL*100)/ACTUAL_COUNT ))%)"
echo "Completed at:       $(date)"
echo "=============================================="