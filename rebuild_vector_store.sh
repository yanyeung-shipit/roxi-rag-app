#!/bin/bash
# Script to start the vector store rebuild process in the background

# Set environment variable for python path
export PYTHONPATH=.

# Check if a maximum number of chunks was specified
MAX_CHUNKS=$1
MAX_CHUNKS_ARG=""

if [ ! -z "$MAX_CHUNKS" ]; then
    MAX_CHUNKS_ARG="$MAX_CHUNKS"
    echo "Will process a maximum of $MAX_CHUNKS chunks"
else
    echo "Will process all chunks until complete"
fi

# Create a timestamp for the log file
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="rebuild_${TIMESTAMP}.log"

echo "Starting vector store rebuild process..."
echo "Log file: $LOG_FILE"
echo "Press Ctrl+C to stop"

# Run the rebuild script in the background with output to log file
nohup python continuous_rebuild.py $MAX_CHUNKS_ARG > $LOG_FILE 2>&1 &

# Save the process ID
PID=$!
echo "Process ID: $PID"
echo "PID $PID" > rebuild_process.pid

echo "Rebuild process started! You can check progress with 'python check_progress.py'"
echo "To stop the process, run: kill \$(cat rebuild_process.pid)"