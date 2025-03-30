#!/bin/bash
# monitor_and_restart_processor.sh
#
# This script monitors the adaptive processor and restarts it if it crashes
# or stops before reaching the target completion percentage.
#
# Usage:
# ./monitor_and_restart_processor.sh
#
# To run in the background:
# nohup ./monitor_and_restart_processor.sh > logs/monitor_66percent.log 2>&1 &

# Configuration
LOG_DIR="logs"
MONITOR_LOG="${LOG_DIR}/monitor_66percent.log"
PROCESSOR_SCRIPT="./run_to_66_percent.sh"
PID_FILE="processor_66_percent.pid"
CHECK_SCRIPT="./check_adaptive_processor.py"
TARGET_PERCENTAGE=66.0
CHECK_INTERVAL=300  # Check every 5 minutes
MAX_INACTIVE_TIME=1800  # 30 minutes
MONITOR_PID_FILE="monitor_66percent.pid"

# Create logs directory if it doesn't exist
mkdir -p "${LOG_DIR}"

# Save our own PID
echo $$ > "${MONITOR_PID_FILE}"

# Function to log messages
log_message() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" >> "${MONITOR_LOG}"
}

# Function to check if the processor is running
check_processor_running() {
    if [ ! -f "${PID_FILE}" ]; then
        log_message "PID file not found. Processor is not running."
        return 1
    fi
    
    pid=$(cat "${PID_FILE}")
    if ! ps -p "${pid}" > /dev/null 2>&1; then
        log_message "Process with PID ${pid} is not running, but PID file exists."
        return 1
    fi
    
    log_message "Processor is running with PID ${pid}."
    return 0
}

# Function to check the completion percentage
check_completion() {
    # Use the check script to get completion percentage
    completion_output=$(python "${CHECK_SCRIPT}" --target "${TARGET_PERCENTAGE}" --json)
    
    # Extract the completion percentage
    percentage=$(echo "${completion_output}" | grep -o '"percentage": [0-9.]*' | grep -o '[0-9.]*')
    
    if [ -z "${percentage}" ]; then
        log_message "Failed to get completion percentage."
        return 1
    fi
    
    log_message "Current completion: ${percentage}%"
    
    # Check if completion is at or above target
    if (( $(echo "${percentage} >= ${TARGET_PERCENTAGE}" | bc -l) )); then
        log_message "Target completion of ${TARGET_PERCENTAGE}% reached!"
        return 0
    else
        log_message "Still processing. Target: ${TARGET_PERCENTAGE}%, Current: ${percentage}%"
        return 1
    fi
}

# Function to check if the processor has made progress recently
check_progress() {
    # Check the last modification time of the checkpoint file
    checkpoint_file="logs/checkpoints/adaptive_processor_checkpoint.pkl"
    
    if [ ! -f "${checkpoint_file}" ]; then
        log_message "Checkpoint file not found."
        return 1
    fi
    
    last_modified=$(stat -c %Y "${checkpoint_file}")
    current_time=$(date +%s)
    time_diff=$((current_time - last_modified))
    
    log_message "Last checkpoint update was ${time_diff} seconds ago."
    
    if [ ${time_diff} -gt ${MAX_INACTIVE_TIME} ]; then
        log_message "WARNING: No progress for ${time_diff} seconds, exceeding maximum inactive time of ${MAX_INACTIVE_TIME} seconds."
        return 1
    fi
    
    return 0
}

# Function to start the processor
start_processor() {
    log_message "Starting processor..."
    
    # Remove stale PID file if it exists
    if [ -f "${PID_FILE}" ]; then
        rm "${PID_FILE}"
    fi
    
    # Start the processor
    ${PROCESSOR_SCRIPT}
    
    # Check if it started successfully
    if check_processor_running; then
        log_message "Processor started successfully."
        return 0
    else
        log_message "Failed to start processor."
        return 1
    fi
}

# Function to stop the processor
stop_processor() {
    if [ ! -f "${PID_FILE}" ]; then
        log_message "PID file not found. Cannot stop processor."
        return 0
    fi
    
    pid=$(cat "${PID_FILE}")
    log_message "Stopping processor with PID ${pid}..."
    
    kill "${pid}" 2>/dev/null
    sleep 2
    
    # Check if it's still running and force kill if necessary
    if ps -p "${pid}" > /dev/null 2>&1; then
        log_message "Processor still running. Force killing..."
        kill -9 "${pid}" 2>/dev/null
        sleep 1
    fi
    
    # Remove PID file
    rm "${PID_FILE}" 2>/dev/null
    
    log_message "Processor stopped."
    return 0
}

# Function to restart the processor
restart_processor() {
    log_message "Restarting processor..."
    stop_processor
    sleep 5
    start_processor
}

# Main monitor loop
main() {
    log_message "===== Starting monitor service ====="
    log_message "Target completion: ${TARGET_PERCENTAGE}%"
    log_message "Check interval: ${CHECK_INTERVAL} seconds"
    log_message "Maximum inactive time: ${MAX_INACTIVE_TIME} seconds"
    
    # First check if we've already reached the target
    if check_completion; then
        log_message "Target already reached. No need to start processor."
        exit 0
    fi
    
    # Start the processor if it's not running
    if ! check_processor_running; then
        log_message "Processor not running. Starting it now."
        start_processor
    fi
    
    # Monitor loop
    while true; do
        log_message "===== Checking status ====="
        
        # Check if we've reached the target
        if check_completion; then
            log_message "Target reached! Stopping monitor service."
            # Clean up before exiting
            rm "${MONITOR_PID_FILE}" 2>/dev/null
            exit 0
        fi
        
        # Check if the processor is running
        if ! check_processor_running; then
            log_message "Processor not running. Restarting..."
            start_processor
        # If it's running, check if it's making progress
        elif ! check_progress; then
            log_message "Processor seems stuck. Restarting..."
            restart_processor
        else
            log_message "Processor is running and making progress. All good."
        fi
        
        log_message "Sleeping for ${CHECK_INTERVAL} seconds..."
        sleep ${CHECK_INTERVAL}
    done
}

# Run the main function
main