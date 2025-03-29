#!/bin/bash
# Script to run the vector store rebuild process continuously until it's complete
# Usage: ./rebuild_until_complete.sh [batch_size] [max_batches] [delay_seconds]

# Default values
BATCH_SIZE=${1:-100}  # Process 100 chunks at a time
MAX_BATCHES=${2:-100}  # Maximum number of batches to run (safety limit)
DELAY_SECONDS=${3:-10}  # Delay between batches in seconds

# Set environment variable for python path
export PYTHONPATH=.

# Create log directory if it doesn't exist
mkdir -p logs

# Create a timestamp for the log files
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="logs/complete_rebuild_${TIMESTAMP}.log"

echo "Starting continuous vector store rebuild process..." | tee -a "$LOG_FILE"
echo "This script will run until all chunks are processed or $MAX_BATCHES batches are completed." | tee -a "$LOG_FILE"
echo "Log file: $LOG_FILE" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Initial progress check
python check_progress.py | tee -a "$LOG_FILE"
INITIAL_PROGRESS=$(python check_progress.py --json | python -c "import json, sys; data = json.load(sys.stdin); print(data['progress_percent'])")
echo "Initial progress: ${INITIAL_PROGRESS}%" | tee -a "$LOG_FILE"

BATCH_COUNT=0
COMPLETE=false

while [ $BATCH_COUNT -lt $MAX_BATCHES ] && [ "$COMPLETE" = false ]; do
    BATCH_COUNT=$((BATCH_COUNT + 1))
    echo "" | tee -a "$LOG_FILE"
    echo "====== STARTING BATCH $BATCH_COUNT ======" | tee -a "$LOG_FILE"
    echo "Running batch with $BATCH_SIZE chunks..." | tee -a "$LOG_FILE"
    
    # Run the process_batches.sh script for one batch
    ./process_batches.sh $BATCH_SIZE 2 false | tee -a "$LOG_FILE"
    
    # Check progress after this batch
    echo "" | tee -a "$LOG_FILE"
    echo "Progress after batch $BATCH_COUNT:" | tee -a "$LOG_FILE"
    python check_progress.py | tee -a "$LOG_FILE"
    
    # Check if we're done
    PROGRESS_DATA=$(python check_progress.py --json)
    CURRENT_PROGRESS=$(echo $PROGRESS_DATA | python -c "import json, sys; data = json.loads(sys.stdin.read()); print(data['progress_percent'])")
    CHUNKS_REMAINING=$(echo $PROGRESS_DATA | python -c "import json, sys; data = json.loads(sys.stdin.read()); print(data['chunks_remaining'])")
    
    echo "Current progress: ${CURRENT_PROGRESS}%" | tee -a "$LOG_FILE"
    echo "Chunks remaining: $CHUNKS_REMAINING" | tee -a "$LOG_FILE"
    
    # Check if we're complete or if there was no progress in this batch
    if [ "$CHUNKS_REMAINING" -le 0 ]; then
        echo "All chunks have been processed!" | tee -a "$LOG_FILE"
        COMPLETE=true
    elif [ $(echo "$CURRENT_PROGRESS >= 99.9" | bc -l) -eq 1 ]; then
        echo "Processing is essentially complete (≥99.9%)!" | tee -a "$LOG_FILE"
        COMPLETE=true
    fi
    
    # If we're not done yet, wait before starting the next batch
    if [ "$COMPLETE" = false ]; then
        echo "Waiting $DELAY_SECONDS seconds before starting next batch..." | tee -a "$LOG_FILE"
        sleep $DELAY_SECONDS
    fi
done

# Final progress check
echo "" | tee -a "$LOG_FILE"
echo "====== FINAL STATUS ======" | tee -a "$LOG_FILE"
python check_progress.py | tee -a "$LOG_FILE"

# Calculate how much we accomplished
FINAL_PROGRESS=$(python check_progress.py --json | python -c "import json, sys; data = json.load(sys.stdin); print(data['progress_percent'])")
PROGRESS_INCREASE=$(echo "$FINAL_PROGRESS - $INITIAL_PROGRESS" | bc -l)

echo "" | tee -a "$LOG_FILE"
echo "Vector store rebuild process completed!" | tee -a "$LOG_FILE"
echo "Ran $BATCH_COUNT batches." | tee -a "$LOG_FILE"
echo "Initial progress: ${INITIAL_PROGRESS}%" | tee -a "$LOG_FILE"
echo "Final progress: ${FINAL_PROGRESS}%" | tee -a "$LOG_FILE"
echo "Progress increased by ${PROGRESS_INCREASE}%" | tee -a "$LOG_FILE"

# Check if we completed everything
if [ "$COMPLETE" = true ]; then
    echo "All chunks successfully processed!" | tee -a "$LOG_FILE"
else
    echo "Maximum number of batches ($MAX_BATCHES) reached before completion." | tee -a "$LOG_FILE"
    echo "Run this script again to continue the rebuild process." | tee -a "$LOG_FILE"
fi

echo "See $LOG_FILE for the complete log." | tee -a "$LOG_FILE"