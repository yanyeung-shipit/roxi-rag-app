#!/bin/bash
# Enhanced Monitor Script for 100% Target
# This script monitors and restarts the enhanced_process_to_100_percent.py script
# if it stops, ensuring continuous processing until the target is reached.

# Log file path
LOG_FILE="enhanced_100percent_monitor.log"

# Function to log messages
log_message() {
    echo "$(date +'%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Function to check if the processor is running
is_processor_running() {
    pgrep -f "python.*enhanced_process_to_100_percent.py" > /dev/null
    return $?
}

# Function to check current progress
check_progress() {
    progress=$(python check_progress.py --json | grep -o '"percentage": [0-9.]*' | cut -d' ' -f2)
    echo $progress
}

# Function to start the processor
start_processor() {
    log_message "Starting enhanced processor to 100%..."
    nohup python enhanced_process_to_100_percent.py --batch-size 3 > enhanced_100percent.log 2>&1 &
    sleep 5
    if is_processor_running; then
        log_message "Processor started successfully with PID $(pgrep -f 'python.*enhanced_process_to_100_percent.py')"
    else
        log_message "Failed to start processor!"
    fi
}

# Main monitoring loop
log_message "Starting enhanced monitor script for 100% target"
log_message "Initial progress: $(check_progress)%"

while true; do
    # Check if we've reached the target
    current_progress=$(check_progress)
    log_message "Current progress: ${current_progress}%"
    
    # If we've reached or exceeded 100%, exit
    if (( $(echo "$current_progress >= 100.0" | bc -l) )); then
        log_message "Target reached! Current progress: ${current_progress}%"
        log_message "Monitoring completed successfully."
        exit 0
    fi
    
    # Check if the processor is running
    if ! is_processor_running; then
        log_message "Processor not running. Restarting..."
        start_processor
    else
        log_message "Processor is running. All good."
    fi
    
    # Wait before checking again
    sleep 60
done