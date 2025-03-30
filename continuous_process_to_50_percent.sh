#!/bin/bash

# Create logs directory if it doesn't exist
mkdir -p logs

# Set the log file path
LOG_FILE="logs/process_50_percent_continuous_$(date +'%Y%m%d_%H%M%S').log"

# Function to check if the process is running
is_running() {
    if [ -f "process_50_percent.pid" ]; then
        PID=$(cat process_50_percent.pid)
        if ps -p $PID > /dev/null; then
            return 0  # Running
        fi
    fi
    return 1  # Not running
}

# Function to start the process
start_process() {
    echo "$(date): Starting processor to reach 50% completion..." >> "$LOG_FILE"
    
    # Start the Python script in the background
    nohup python -u process_to_50_percent.py >> "$LOG_FILE" 2>&1 &
    
    # Get the PID
    PID=$!
    echo "$PID" > "process_50_percent.pid"
    
    echo "$(date): Process started with PID: $PID" >> "$LOG_FILE"
}

# Function to check progress
check_progress() {
    local progress
    if grep -q "Progress:" "$LOG_FILE"; then
        progress=$(grep "Progress:" "$LOG_FILE" | tail -1)
        echo "$(date): Current $progress" >> "$LOG_FILE"
    else
        echo "$(date): No progress information found yet" >> "$LOG_FILE"
    fi
}

# Main loop
echo "Starting continuous processing to 50% completion..."
echo "Log file: $LOG_FILE"
echo "Press Ctrl+C to stop"

# Initial start
start_process

# Keep checking and restarting if needed
while true; do
    if ! is_running; then
        echo "$(date): Process stopped, restarting..." >> "$LOG_FILE"
        start_process
    else
        check_progress
    fi
    
    # Check if 50% has been reached
    if grep -q "Target percentage of 50.0% reached" "$LOG_FILE"; then
        echo "$(date): Target of 50% reached! Processing complete." >> "$LOG_FILE"
        echo "Target of 50% reached! Processing complete."
        break
    fi
    
    # Sleep for 60 seconds before checking again
    sleep 60
done

echo "Continuous processing completed successfully."