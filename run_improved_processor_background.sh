#!/bin/bash

# Run Improved Processor Script in Background
# This script runs the improved continuous processor with the optimal settings for Replit
# It runs in the background and continuously monitors and restarts the processor if needed

echo "Starting improved continuous processor in background..."
echo "Target: 40% completion"
echo "Batch size: 1 chunk"
echo "Delay: 3 seconds between chunks"

# Kill any existing processor instances
pkill -f "improved_continuous_processor.py" || true

# Wait for processes to terminate
sleep 2

# Start the processor in the background
nohup python improved_continuous_processor.py --batch-size 1 --delay 3 --target 40 > improved_processor_output.log 2>&1 &
PROCESSOR_PID=$!

echo "Processor started with PID: $PROCESSOR_PID"
echo "Logging output to: improved_processor_output.log"

# Function to check if a process is running
is_process_running() {
    ps -p $1 > /dev/null
    return $?
}

# Create a simple monitor loop
echo "Starting monitor loop..."
while true; do
    if ! is_process_running $PROCESSOR_PID; then
        echo "$(date): Processor is not running. Restarting..."
        
        # Start the processor again
        nohup python improved_continuous_processor.py --batch-size 1 --delay 3 --target 40 >> improved_processor_output.log 2>&1 &
        PROCESSOR_PID=$!
        
        echo "$(date): Processor restarted with PID: $PROCESSOR_PID"
    else
        echo "$(date): Processor is running with PID: $PROCESSOR_PID"
    fi
    
    # Check the progress
    CURRENT_PROGRESS=$(grep "Progress:" improved_processor_output.log | tail -n 1)
    echo "Current progress: $CURRENT_PROGRESS"
    
    # Sleep for 60 seconds before checking again
    sleep 60
done