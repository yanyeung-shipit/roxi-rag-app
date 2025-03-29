#!/bin/bash
# Process multiple chunks in sequence, one at a time
# This script is designed to be more reliable by processing chunks individually

# Configuration
LAST_ID=${1:-6681}  # Default to last ID we processed
BATCH_SIZE=${2:-10}  # Default to 10 chunks per batch
LOG_DIR="logs/batch_processing"
LOG_PREFIX="chunks_sequential_$(date +%Y%m%d_%H%M%S)"
MASTER_LOG="$LOG_DIR/${LOG_PREFIX}_master.log"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Log the start
echo "======================================================" | tee -a "$MASTER_LOG"
echo "SEQUENTIAL PROCESSING START: $(date +%Y%m%d_%H%M%S)" | tee -a "$MASTER_LOG"
echo "Last processed ID: $LAST_ID" | tee -a "$MASTER_LOG"
echo "Batch size: $BATCH_SIZE" | tee -a "$MASTER_LOG"
echo "======================================================" | tee -a "$MASTER_LOG"

# Check initial state
echo "Initial state:" | tee -a "$MASTER_LOG"
python check_progress.py | tee -a "$MASTER_LOG"
echo "" | tee -a "$MASTER_LOG"

# Get the next chunks to process
echo "Getting next chunks to process after ID $LAST_ID..." | tee -a "$MASTER_LOG"
NEXT_CHUNKS=$(python get_next_chunks.py $LAST_ID --limit $BATCH_SIZE)

# Count how many chunks we got
CHUNK_COUNT=$(echo "$NEXT_CHUNKS" | wc -l)
echo "Found $CHUNK_COUNT chunks to process" | tee -a "$MASTER_LOG"

# Process each chunk one at a time
if [ -n "$NEXT_CHUNKS" ]; then
    echo "Processing $CHUNK_COUNT chunks..." | tee -a "$MASTER_LOG"
    success_count=0
    failure_count=0
    
    echo "$NEXT_CHUNKS" | while read -r chunk_id; do
        echo "Processing chunk $chunk_id..." | tee -a "$MASTER_LOG"
        
        # Process this chunk
        if ./process_single_chunk.sh $chunk_id; then
            echo "Successfully processed chunk $chunk_id" | tee -a "$MASTER_LOG"
            ((success_count++))
            # Update the last processed ID
            LAST_ID=$chunk_id
        else
            echo "Failed to process chunk $chunk_id" | tee -a "$MASTER_LOG"
            ((failure_count++))
        fi
        
        # Wait a moment between chunks (to avoid overloading the system)
        sleep 1
    done
    
    echo "Processed $success_count chunks successfully, $failure_count failures" | tee -a "$MASTER_LOG"
else
    echo "No chunks found to process" | tee -a "$MASTER_LOG"
fi

# Check final state
echo "" | tee -a "$MASTER_LOG"
echo "Final state:" | tee -a "$MASTER_LOG"
python check_progress.py | tee -a "$MASTER_LOG"

echo "Sequential processing completed at $(date)" | tee -a "$MASTER_LOG"
echo "Log file: $MASTER_LOG"
echo "Last processed ID: $LAST_ID"

# Output the last processed ID for the next run
echo $LAST_ID