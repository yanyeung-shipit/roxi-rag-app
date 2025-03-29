#!/bin/bash
# Process chunks until reaching a target percentage of completion
# Usage: ./process_to_target.sh [target_percentage] [start_chunk_id] [max_chunks]

# Set defaults
TARGET_PERCENTAGE=${1:-65.0}
START_CHUNK_ID=${2:-6725}  # Use next chunk after the 30 we're processing
MAX_CHUNKS=${3:-200}        # Safety limit to avoid infinite loops

# Set up logging
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="logs/batch_processing/target_${TARGET_PERCENTAGE}_${TIMESTAMP}.log"
mkdir -p "logs/batch_processing"

# Function to get current percentage using check_progress.py with JSON output
get_current_percentage() {
    python -c '
import json
import subprocess

result = subprocess.run(["python", "check_progress.py", "--json"], 
                        capture_output=True, text=True)
try:
    data = json.loads(result.stdout.strip())
    print(data["progress_pct"])
except (json.JSONDecodeError, KeyError) as e:
    print("0.0")  # Default if we cannot parse
'
}

# Log header
echo "======================================================" | tee -a "$LOG_FILE"
echo "TARGET PERCENTAGE PROCESSING" | tee -a "$LOG_FILE"
echo "Target: ${TARGET_PERCENTAGE}%" | tee -a "$LOG_FILE"
echo "Start chunk: $START_CHUNK_ID" | tee -a "$LOG_FILE"
echo "Max chunks: $MAX_CHUNKS" | tee -a "$LOG_FILE"
echo "Start time: $(date)" | tee -a "$LOG_FILE"
echo "======================================================" | tee -a "$LOG_FILE"

# Get initial progress
python check_progress.py | tee -a "$LOG_FILE"

# Initial percentage
CURRENT_PERCENTAGE=$(get_current_percentage)
echo "Initial percentage: ${CURRENT_PERCENTAGE}%" | tee -a "$LOG_FILE"

# Process chunks until target is reached
CURRENT_ID=$START_CHUNK_ID
CHUNKS_PROCESSED=0
SUCCESSFUL=0

while (( $(echo "$CURRENT_PERCENTAGE < $TARGET_PERCENTAGE" | bc -l) )) && 
      (( CHUNKS_PROCESSED < MAX_CHUNKS )); do
    
    echo "-----------------------------------------------------" | tee -a "$LOG_FILE"
    echo "Processing chunk $CURRENT_ID (${CURRENT_PERCENTAGE}% complete, target: ${TARGET_PERCENTAGE}%)" | tee -a "$LOG_FILE"
    
    # Process the chunk
    ./process_single_chunk.sh $CURRENT_ID >> "$LOG_FILE" 2>&1
    
    # Check result
    if [ $? -eq 0 ]; then
        echo "✓ Successfully processed chunk $CURRENT_ID" | tee -a "$LOG_FILE"
        SUCCESSFUL=$((SUCCESSFUL + 1))
    else
        echo "✗ Failed to process chunk $CURRENT_ID" | tee -a "$LOG_FILE"
    fi
    
    # Increment counters
    CHUNKS_PROCESSED=$((CHUNKS_PROCESSED + 1))
    CURRENT_ID=$((CURRENT_ID + 1))
    
    # Get updated percentage
    CURRENT_PERCENTAGE=$(get_current_percentage)
    
    # Status update every 5 chunks
    if (( CHUNKS_PROCESSED % 5 == 0 )); then
        echo "-----------------------------------------------------" | tee -a "$LOG_FILE"
        echo "PROGRESS UPDATE" | tee -a "$LOG_FILE"
        echo "Chunks processed: $CHUNKS_PROCESSED ($SUCCESSFUL successful)" | tee -a "$LOG_FILE"
        echo "Current percentage: ${CURRENT_PERCENTAGE}% (target: ${TARGET_PERCENTAGE}%)" | tee -a "$LOG_FILE"
        echo "-----------------------------------------------------" | tee -a "$LOG_FILE"
    fi
    
    # Small delay to avoid overloading
    sleep 1
done

# Final status
echo "======================================================" | tee -a "$LOG_FILE"
echo "PROCESSING COMPLETE" | tee -a "$LOG_FILE"
echo "Final percentage: ${CURRENT_PERCENTAGE}% (target: ${TARGET_PERCENTAGE}%)" | tee -a "$LOG_FILE"
echo "Total chunks processed: $CHUNKS_PROCESSED" | tee -a "$LOG_FILE"
echo "Successful chunks: $SUCCESSFUL" | tee -a "$LOG_FILE"
echo "End time: $(date)" | tee -a "$LOG_FILE"
echo "======================================================" | tee -a "$LOG_FILE"

# Final progress check
python check_progress.py | tee -a "$LOG_FILE"

echo "Log file: $LOG_FILE"

# Exit with success if we reached the target
if (( $(echo "$CURRENT_PERCENTAGE >= $TARGET_PERCENTAGE" | bc -l) )); then
    echo "Target percentage of ${TARGET_PERCENTAGE}% reached successfully!" | tee -a "$LOG_FILE"
    exit 0
else
    echo "Did not reach target percentage after $MAX_CHUNKS chunks. Current: ${CURRENT_PERCENTAGE}%" | tee -a "$LOG_FILE"
    exit 1
fi