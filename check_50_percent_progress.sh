#!/bin/bash

# Check if PID file exists
if [ -f "process_50_percent.pid" ]; then
    PID=$(cat process_50_percent.pid)
    
    # Check if process is still running
    if ps -p $PID > /dev/null; then
        echo "Processor is running with PID: $PID"
    else
        echo "Processor is not running (stale PID file)"
    fi
else
    echo "Processor is not running (no PID file)"
fi

echo -e "\nRecent log entries:"
echo "-------------------"

# Find the most recent log file
latest_log=$(ls -t logs/process_50_percent_continuous_* 2>/dev/null | head -1)

if [ -n "$latest_log" ] && [ -f "$latest_log" ]; then
    # Extract progress information
    progress=$(grep "Progress:" "$latest_log" | tail -1)
    
    if [ -n "$progress" ]; then
        echo "$progress"
    else
        echo "No progress information found in log"
    fi
    
    # Show the most recent log entries
    echo -e "\nLatest log entries:"
    tail -10 "$latest_log"
else
    echo "No log files found"
fi

echo -e "\nTo restart processing, run: ./continuous_process_to_50_percent.sh"