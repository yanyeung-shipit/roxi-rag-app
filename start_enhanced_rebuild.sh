#!/bin/bash
# Start the enhanced rebuild process in the background

# Create logs directory if it doesn't exist
mkdir -p logs

# Get current timestamp
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Set up the log file
LOG_FILE="logs/enhanced_rebuild_${TIMESTAMP}.log"

echo "Starting enhanced vector store rebuild in the background..."
echo "Logs will be written to ${LOG_FILE}"

# Start the rebuild process in the background
nohup python3 enhanced_rebuild.py "$@" > "${LOG_FILE}" 2>&1 &

# Save the process ID
PID=$!
echo "Process started with PID: ${PID}"
echo "${PID}" > enhanced_rebuild.pid

echo "To monitor progress, use: tail -f ${LOG_FILE}"
echo "To stop the process, use: kill $(cat enhanced_rebuild.pid)"