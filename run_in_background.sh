#!/bin/bash

# Run the simplified processor in background with nohup
# This script will ensure the processor runs reliably in the background

# Kill any existing processors
pkill -f simplified_processor.py || true

# Create log directory if it doesn't exist
mkdir -p logs

# Get timestamp for unique log file
TIMESTAMP=$(date +%Y%m%d%H%M%S)
LOG_FILE="logs/processor_${TIMESTAMP}.log"

# Start the processor with nohup
echo "Starting simplified processor in background..."
nohup python simplified_processor.py --delay 3 > "$LOG_FILE" 2>&1 &
PID=$!

# Save PID to file for later reference
echo $PID > processor.pid

echo "Process started with PID: $PID"
echo "Logging to: $LOG_FILE"
echo "To monitor progress: tail -f $LOG_FILE"
echo "To stop the processor: kill \$(cat processor.pid)"

# Wait a moment to confirm it's running
sleep 2
if ps -p $PID > /dev/null; then
    echo "Processor is running successfully."
else
    echo "ERROR: Processor failed to start."
    exit 1
fi