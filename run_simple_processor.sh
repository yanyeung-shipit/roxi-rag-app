#!/bin/bash

# Run Simple Processor Script
# This script runs the simple chunk processor with optimal settings

echo "Starting simple chunk processor..."
echo "Target: 40% completion"
echo "Delay: 3 seconds between chunks"

# Make the processor executable
chmod +x simple_chunk_processor.py

# Start the processor and log output
./simple_chunk_processor.py --target 40 --delay 3 > simple_processor_output.log 2>&1 &
PROCESSOR_PID=$!

echo "Processor started with PID: $PROCESSOR_PID"
echo "Logging to: simple_processor_output.log"
echo "To monitor progress: tail -f simple_processor_output.log"
echo

# Wait a moment to check if it's running
sleep 5

if ps -p $PROCESSOR_PID > /dev/null; then
    echo "Processor is running successfully."
else
    echo "Processor failed to start or exited quickly."
    echo "Check the log file for details."
fi