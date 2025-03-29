#!/bin/bash
# This script starts a background rebuild process and detaches it from the terminal
# Usage: ./start_background_rebuild.sh [batch_size] [max_batches] [delay_seconds]

# Default values
BATCH_SIZE=${1:-50}  # Process 50 chunks at a time
MAX_BATCHES=${2:-100}  # Maximum 100 batches (5000 chunks total)
DELAY_SECONDS=${3:-5}  # 5 seconds between batches

# Create a timestamp 
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create log directory if it doesn't exist
mkdir -p logs

# Create a PID file to track the background process
PID_FILE="rebuild_process.pid"

# Check if another rebuild process is already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p $PID > /dev/null; then
        echo "A rebuild process is already running with PID $PID."
        echo "If you believe this is incorrect, delete $PID_FILE and try again."
        exit 1
    else
        echo "Found stale PID file. Previous process is no longer running."
        rm "$PID_FILE"
    fi
fi

# Start the rebuild process in the background
echo "Starting background rebuild process..."
echo "Batch size: $BATCH_SIZE chunks"
echo "Max batches: $MAX_BATCHES"
echo "Delay between batches: $DELAY_SECONDS seconds"
echo "Output will be logged to logs/background_rebuild_${TIMESTAMP}.log"

# Start the process in the background
nohup ./rebuild_until_complete.sh "$BATCH_SIZE" "$MAX_BATCHES" "$DELAY_SECONDS" > "logs/background_rebuild_${TIMESTAMP}.log" 2>&1 &

# Save the PID
BG_PID=$!
echo "PID $BG_PID" > "$PID_FILE"
echo "Background process started with PID $BG_PID"
echo "Use 'tail -f logs/background_rebuild_${TIMESTAMP}.log' to monitor progress"
echo "Use 'kill $BG_PID' to stop the process if needed"

# Check progress before exiting
echo ""
echo "Initial vector store status:"
PYTHONPATH=. python check_progress.py