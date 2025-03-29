#!/bin/bash
# Process N chunks sequentially
# Usage: ./process_n_chunks.sh [starting_chunk_id] [number_of_chunks]

# Get parameters with defaults
STARTING_CHUNK_ID=${1:-6695}
NUM_CHUNKS=${2:-10}
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="logs/batch_processing/chunks_n_${TIMESTAMP}.log"

# Create log directory if it doesn't exist
mkdir -p "logs/batch_processing"

# Log header
echo "=====================================================" > "$LOG_FILE"
echo "PROCESSING $NUM_CHUNKS CHUNKS FROM ID $STARTING_CHUNK_ID" >> "$LOG_FILE"
echo "START TIME: $(date)" >> "$LOG_FILE"
echo "=====================================================" >> "$LOG_FILE"

# Initial progress
python check_progress.py | tee -a "$LOG_FILE"
echo "-----------------------------------------------------" >> "$LOG_FILE"

# Process chunks
CURRENT_ID=$STARTING_CHUNK_ID
SUCCESSFUL=0

for ((i=1; i<=$NUM_CHUNKS; i++)); do
    echo "Processing chunk $CURRENT_ID ($i of $NUM_CHUNKS)..." | tee -a "$LOG_FILE"
    
    # Process single chunk
    ./process_single_chunk.sh $CURRENT_ID >> "$LOG_FILE" 2>&1
    
    # Check result
    if [ $? -eq 0 ]; then
        echo "✓ Successfully processed chunk $CURRENT_ID" | tee -a "$LOG_FILE"
        SUCCESSFUL=$((SUCCESSFUL + 1))
        # Increment chunk ID for next iteration
        CURRENT_ID=$((CURRENT_ID + 1))
    else
        echo "✗ Failed to process chunk $CURRENT_ID, skipping to next..." | tee -a "$LOG_FILE"
        # Skip to next chunk ID
        CURRENT_ID=$((CURRENT_ID + 1))
    fi
    
    # Status update every 5 chunks
    if (( i % 5 == 0 )) || (( i == NUM_CHUNKS )); then
        echo "-----------------------------------------------------" | tee -a "$LOG_FILE"
        echo "PROGRESS: $i of $NUM_CHUNKS chunks processed ($SUCCESSFUL successful)" | tee -a "$LOG_FILE"
        python check_progress.py | grep "Vector store:" | tee -a "$LOG_FILE"
        python check_progress.py | grep "complete" | tee -a "$LOG_FILE"
        echo "-----------------------------------------------------" | tee -a "$LOG_FILE"
    fi
    
    # Small delay to avoid overloading
    sleep 1
done

# Final progress
echo "=====================================================" | tee -a "$LOG_FILE"
echo "PROCESSING COMPLETE" | tee -a "$LOG_FILE"
echo "TOTAL CHUNKS PROCESSED: $NUM_CHUNKS" | tee -a "$LOG_FILE"
echo "SUCCESSFUL CHUNKS: $SUCCESSFUL" | tee -a "$LOG_FILE"
echo "END TIME: $(date)" | tee -a "$LOG_FILE"
echo "=====================================================" | tee -a "$LOG_FILE"

# Final progress check
python check_progress.py | tee -a "$LOG_FILE"

echo "Log file: $LOG_FILE"