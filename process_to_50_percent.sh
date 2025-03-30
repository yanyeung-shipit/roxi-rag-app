#!/bin/bash

# Create logs directory if it doesn't exist
mkdir -p logs

# Set the log file path
LOG_FILE="logs/process_50_percent_$(date +'%Y%m%d_%H%M%S').log"

# Run the Python script in the background with nohup
echo "Starting processor to reach 50% completion..." 
echo "Log file: $LOG_FILE"

# Run with nohup to keep it running even if terminal closes
nohup python -u process_to_50_percent.py > "$LOG_FILE" 2>&1 &

# Get the PID
PID=$!
echo "Process started with PID: $PID"
echo "$PID" > "process_50_percent.pid"

echo "Process is running in the background."
echo "Monitor progress with: tail -f $LOG_FILE"