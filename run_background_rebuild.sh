#!/bin/bash

# Script to run the batch rebuild process in the background
# This script will keep running even if the connection is lost

# Create logs directory
mkdir -p logs/rebuild

# Get timestamp for log files
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Parameters with defaults
BATCH_SIZE=${1:-5}        # Number of chunks per batch
DELAY=${2:-3}             # Seconds between processing chunks
RUNTIME=${3:-14400}       # Maximum runtime in seconds (default: 4 hours)

echo "Starting background rebuild process at $(date)"
echo "Parameters: BATCH_SIZE=$BATCH_SIZE, DELAY=$DELAY, RUNTIME=$RUNTIME"
echo "Logs will be saved to: logs/rebuild/background_rebuild_$TIMESTAMP.log"

# Run the batch rebuild script with nohup to keep it running after disconnect
nohup ./batch_rebuild.sh "$BATCH_SIZE" "$DELAY" "$RUNTIME" > "logs/rebuild/background_rebuild_$TIMESTAMP.log" 2>&1 &

# Save the process ID
echo $! > "logs/rebuild/rebuild_process.pid"

echo "Background process started with PID: $(cat logs/rebuild/rebuild_process.pid)"
echo "To check progress: tail -f logs/rebuild/background_rebuild_$TIMESTAMP.log"
echo "To stop the process: kill $(cat logs/rebuild/rebuild_process.pid)"