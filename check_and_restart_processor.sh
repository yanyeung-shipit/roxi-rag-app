#!/bin/bash

# Script to check if the processor is running and restart it if needed
# This is meant to be run periodically from a crontab or similar scheduler
# or manually if you notice the processor has stopped

# Configuration
TARGET_PERCENTAGE=50.0
PROCESSOR_SCRIPT="python process_to_50_percent.py"
LOG_FILE="process_to_50_percent.log"
MONITOR_LOG="processor_monitor.log"
PID_FILE="process_50_percent.pid"

# Function to check current progress
check_progress() {
    progress_output=$(python check_progress.py)
    current_percentage=$(echo "$progress_output" | grep -o '[0-9]\+\.[0-9]\+%' | head -1 | sed 's/%//')
    # If no percentage found, default to 0
    if [ -z "$current_percentage" ]; then
        current_percentage="0.0"
    fi
    echo "$current_percentage"
}

# Log with timestamp
log_message() {
    echo "$(date +'%Y-%m-%d %H:%M:%S') - $1" | tee -a "$MONITOR_LOG"
}

# Check if the processor is running
is_processor_running() {
    # First check using pgrep for both scripts
    if pgrep -f "batch_rebuild_to_target.py" > /dev/null || pgrep -f "process_to_50_percent.py" > /dev/null; then
        return 0  # Running based on process name
    fi
    
    # Then check using PID file if it exists
    if [ -f "$PID_FILE" ]; then
        pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null; then
            return 0  # Running based on PID file
        else
            # PID file exists but process is not running, clean up
            log_message "PID file exists but process is not running. Cleaning up."
            rm -f "$PID_FILE"
        fi
    fi
    
    return 1  # Not running
}

# Main function
main() {
    log_message "Checking processor status..."
    
    # Check current progress
    current=$(check_progress)
    log_message "Current progress: ${current}%"
    
    # If target reached, we're done
    if (( $(echo "$current >= $TARGET_PERCENTAGE" | bc -l) )); then
        log_message "Target reached: ${current}% complete. No need to restart."
        return 0
    fi
    
    # Check if processor is running
    if is_processor_running; then
        log_message "Processor is running. No action needed."
        return 0
    else
        log_message "Processor is not running. Restarting..."
        nohup $PROCESSOR_SCRIPT >> "$LOG_FILE" 2>&1 &
        pid=$!
        echo $pid > "$PID_FILE"
        log_message "Started new processor with PID: $pid (saved to $PID_FILE)"
    fi
}

# Run the main function
main

exit 0