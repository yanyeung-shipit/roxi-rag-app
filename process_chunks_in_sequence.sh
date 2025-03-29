#!/bin/bash

# process_chunks_in_sequence.sh
# This script processes chunks one at a time in sequence until a target percentage is reached
# or a maximum number of chunks is processed.
#
# Usage: ./process_chunks_in_sequence.sh [start_chunk_id] [max_chunks] [target_percentage]
#   start_chunk_id: The chunk ID to start processing from (optional)
#   max_chunks: Maximum number of chunks to process (default: 20)
#   target_percentage: Target percentage to reach (optional)

# Set default values
MAX_CHUNKS=${2:-20}
TARGET_PERCENTAGE=${3:-0}
CURRENT_CHUNK=${1:-$(python -c "import sys; from models import db, DocumentChunk; print(DocumentChunk.query.filter(DocumentChunk.is_processed==False).order_by(DocumentChunk.id).first().id)")}

# Create log directory if it doesn't exist
mkdir -p logs/sequential_processing

# Generate timestamp for log files
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="logs/sequential_processing/sequence_${TIMESTAMP}.log"

echo "======================================================" | tee -a "$LOG_FILE"
echo "SEQUENTIAL CHUNK PROCESSING" | tee -a "$LOG_FILE"
echo "Start Chunk: $CURRENT_CHUNK" | tee -a "$LOG_FILE"
echo "Max Chunks: $MAX_CHUNKS" | tee -a "$LOG_FILE"
echo "Target: $TARGET_PERCENTAGE%" | tee -a "$LOG_FILE"
echo "Start time: $(date)" | tee -a "$LOG_FILE"
echo "======================================================" | tee -a "$LOG_FILE"

# Get initial progress
initial_progress=$(python check_progress.py | grep 'complete' | grep -o '[0-9.]*')
echo "Initial progress: $initial_progress%" | tee -a "$LOG_FILE"

# Process chunks one at a time
chunks_processed=0
while [ $chunks_processed -lt $MAX_CHUNKS ]; do
    # Check if we've reached the target percentage
    if (( $(echo "$TARGET_PERCENTAGE > 0" | bc -l) )); then
        current_progress=$(python check_progress.py | grep 'complete' | grep -o '[0-9.]*')
        echo "Current progress: $current_progress% (Target: $TARGET_PERCENTAGE%)" | tee -a "$LOG_FILE"
        
        # Check if we've reached or exceeded the target percentage
        if (( $(echo "$current_progress >= $TARGET_PERCENTAGE" | bc -l) )); then
            echo "Target percentage reached: $current_progress%" | tee -a "$LOG_FILE"
            break
        fi
    fi
    
    echo "Processing chunk $CURRENT_CHUNK ($(($chunks_processed + 1)) of $MAX_CHUNKS)..." | tee -a "$LOG_FILE"
    
    # Process the chunk
    ./process_single_chunk.sh $CURRENT_CHUNK >> "$LOG_FILE" 2>&1
    
    # Check if processing succeeded
    if [ $? -eq 0 ]; then
        echo "✓ Successfully processed chunk $CURRENT_CHUNK" | tee -a "$LOG_FILE"
        chunks_processed=$((chunks_processed + 1))
    else
        echo "✗ Failed to process chunk $CURRENT_CHUNK" | tee -a "$LOG_FILE"
    fi
    
    # Get the next chunk ID
    CURRENT_CHUNK=$((CURRENT_CHUNK + 1))
    
    # Add a short delay to prevent rate limiting
    sleep 1
done

# Get final progress
final_progress=$(python check_progress.py | grep -o '[0-9.]*% complete' | grep -o '[0-9.]*')

echo "======================================================" | tee -a "$LOG_FILE"
echo "SEQUENTIAL PROCESSING COMPLETE" | tee -a "$LOG_FILE"
echo "Chunks processed: $chunks_processed" | tee -a "$LOG_FILE"
echo "Final progress: $final_progress% (started at $initial_progress%)" | tee -a "$LOG_FILE"
echo "End time: $(date)" | tee -a "$LOG_FILE"
echo "======================================================" | tee -a "$LOG_FILE"

echo "Process complete. See $LOG_FILE for details."