#!/bin/bash

# Stop any existing processing
pkill -f "python process_to_75_percent.py" 2>/dev/null

# Clear log
echo "Starting process_to_75_percent.py at $(date)" > process_75_percent_enhanced.log

# Run the script with nohup to keep it running even if the terminal is closed
nohup python process_to_75_percent.py --batch-size 5 --target 75.0 --delay 3 >> process_75_percent_enhanced.log 2>&1 &

# Store the process ID
PID=$!
echo $PID > rebuild_process.pid

echo "Started process_to_75_percent.py with PID $PID"
echo "Log file: process_75_percent_enhanced.log"
echo ""
echo "To check progress, run: python process_to_75_percent.py --check"
echo "To monitor the log, run: tail -f process_75_percent_enhanced.log"