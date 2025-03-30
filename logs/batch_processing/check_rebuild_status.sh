#!/bin/bash
# Script to check the status of the background rebuild process

PID_FILE="logs/batch_processing/background_rebuild.pid"
LOG_FILE="logs/batch_processing/background_rebuild_20250330_001151.log"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p $PID > /dev/null; then
        echo "Rebuild process is running with PID $PID"
        echo "Recent log entries:"
        tail -n 10 "$LOG_FILE"
        
        # Check progress
        echo -e "\nCurrent progress:"
        python check_progress.py
    else
        echo "No rebuild process is running. The PID file exists but process $PID is not active."
        echo "Final log entries:"
        tail -n 20 "$LOG_FILE"
        
        # Check progress
        echo -e "\nFinal progress:"
        python check_progress.py
    fi
else
    echo "No rebuild process is currently tracked."
    
    # Check progress
    echo -e "\nCurrent progress:"
    python check_progress.py
fi
