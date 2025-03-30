#!/bin/bash
# enhanced_monitor.sh
#
# This enhanced monitor script continuously checks if the processor is running
# and restarts it if it's not, with more robust error handling and recovery mechanisms.
#
# Usage:
# ./enhanced_monitor.sh
#
# To run in the background:
# nohup ./enhanced_monitor.sh > logs/enhanced_monitor.log 2>&1 &

# Configuration
LOG_DIR="logs"
MONITOR_LOG="${LOG_DIR}/enhanced_monitor.log"
PROCESSOR_SCRIPT="processors/adaptive_processor.py"
PID_FILE="processor_66_percent.pid"
TARGET_PERCENTAGE=66.0
MAX_RETRIES=10
RETRY_DELAY=10  # seconds
CHECK_INTERVAL=15  # Check every 15 seconds
MONITOR_PID_FILE="enhanced_monitor.pid"
CHECKPOINT_DIR="${LOG_DIR}/checkpoints"
CHECKPOINT_FILE="${CHECKPOINT_DIR}/adaptive_processor_checkpoint.pkl"
LOG_TIMESTAMP=$(date +%Y%m%d-%H%M%S)
PROCESSOR_LOG="${LOG_DIR}/processor_66_percent_${LOG_TIMESTAMP}.log"

# Create logs directory if it doesn't exist
mkdir -p "${LOG_DIR}"
mkdir -p "${CHECKPOINT_DIR}"

# Save our own PID
echo $$ > "${MONITOR_PID_FILE}"
trap 'rm -f ${MONITOR_PID_FILE}' EXIT

# Function to log messages
log_message() {
    local timestamp=$(date +'%Y-%m-%d %H:%M:%S')
    echo "[${timestamp}] $1"
    echo "[${timestamp}] $1" >> "${MONITOR_LOG}"
}

# Function to get current processor progress from checkpoint file
get_progress() {
    # Check if the checkpoint file exists
    if [ ! -f "${CHECKPOINT_FILE}" ]; then
        echo "0.0"
        return
    fi
    
    # Use python to extract the progress percentage
    python -c "
import pickle
try:
    with open('${CHECKPOINT_FILE}', 'rb') as f:
        checkpoint = pickle.load(f)
        processed = len(checkpoint['processed_chunk_ids'])
        total_chunks = 1261  # Hardcoded based on previous logs
        print(f'{(processed / total_chunks) * 100:.1f}')
except Exception as e:
    print(f'0.0')
" 2>/dev/null || echo "0.0"
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
        rm -f "${PID_FILE}"  # Remove stale PID file
        return 1
    fi
    
    log_message "Processor is running with PID ${pid}."
    return 0
}

# Function to start the processor
start_processor() {
    log_message "Starting processor to reach ${TARGET_PERCENTAGE}% completion..."
    
    # Remove stale PID file if it exists
    if [ -f "${PID_FILE}" ]; then
        rm -f "${PID_FILE}"
    fi
    
    # Start the processor with its output redirected to the log file
    log_message "Running: python ${PROCESSOR_SCRIPT} --target ${TARGET_PERCENTAGE} > ${PROCESSOR_LOG} 2>&1 &"
    python "${PROCESSOR_SCRIPT}" --target "${TARGET_PERCENTAGE}" > "${PROCESSOR_LOG}" 2>&1 &
    processor_pid=$!
    
    # Save the PID to the PID file
    echo ${processor_pid} > "${PID_FILE}"
    log_message "Processor started with PID ${processor_pid}"
    
    # Wait a moment to check if the process is still running
    sleep 3
    if ! ps -p "${processor_pid}" > /dev/null 2>&1; then
        log_message "Processor failed to start. Check the log file: ${PROCESSOR_LOG}"
        rm -f "${PID_FILE}" 2>/dev/null
        return 1
    fi
    
    log_message "Processor started successfully."
    return 0
}

# Function to check if target percentage has been reached
check_target_reached() {
    current_progress=$(get_progress)
    log_message "Current progress: ${current_progress}%"
    
    # Check if the progress has reached the target
    if (( $(echo "${current_progress} >= ${TARGET_PERCENTAGE}" | bc -l) )); then
        log_message "Target of ${TARGET_PERCENTAGE}% reached! Current progress: ${current_progress}%"
        return 0
    else
        log_message "Still processing. Target: ${TARGET_PERCENTAGE}%, Current: ${current_progress}%"
        return 1
    fi
}

# Function to check if the processor is making progress
check_progress() {
    # Get the last modification time of the checkpoint file
    if [ ! -f "${CHECKPOINT_FILE}" ]; then
        log_message "WARNING: Checkpoint file not found!"
        return 1
    fi
    
    # Get last modified timestamp
    last_modified=$(stat -c %Y "${CHECKPOINT_FILE}")
    current_time=$(date +%s)
    time_diff=$((current_time - last_modified))
    
    log_message "Last checkpoint update was ${time_diff} seconds ago."
    
    # If no update in last 5 minutes, consider it stuck
    if [ ${time_diff} -gt 300 ]; then
        log_message "WARNING: No progress for ${time_diff} seconds (>5 minutes). Processor may be stuck."
        return 1
    fi
    
    return 0
}

# Main function
main() {
    log_message "=== ENHANCED MONITOR STARTED ==="
    log_message "Target completion: ${TARGET_PERCENTAGE}%"
    log_message "Check interval: ${CHECK_INTERVAL} seconds"
    log_message "Processor log: ${PROCESSOR_LOG}"
    
    # Check if we've already reached the target
    if check_target_reached; then
        log_message "Target already reached! No need to run processor."
        exit 0
    fi
    
    # First attempt to start the processor
    if ! check_processor_running; then
        log_message "Processor not running. Starting it now."
        if ! start_processor; then
            log_message "Failed to start processor on first attempt."
        fi
    fi
    
    # Retry counter for consecutive failures
    consecutive_failures=0
    
    # Main monitoring loop
    while true; do
        log_message "--- Monitoring Check ---"
        
        # Check if target has been reached
        if check_target_reached; then
            log_message "=== TARGET REACHED! SHUTTING DOWN MONITOR ==="
            exit 0
        fi
        
        # Check if processor is running
        if ! check_processor_running; then
            log_message "Processor not running. Attempting to restart."
            if ! start_processor; then
                consecutive_failures=$((consecutive_failures + 1))
                log_message "Failed to restart processor. Consecutive failures: ${consecutive_failures}"
                
                # If too many consecutive failures, increase delay
                if [ ${consecutive_failures} -gt 3 ]; then
                    retry_delay=$((RETRY_DELAY * 2))
                    log_message "Multiple restart failures. Increasing delay to ${retry_delay} seconds."
                    sleep ${retry_delay}
                    continue
                fi
            else
                consecutive_failures=0
            fi
        # If processor is running, check if it's making progress
        elif ! check_progress; then
            log_message "Processor is running but appears stuck. Restarting..."
            
            # Kill the current process
            pid=$(cat "${PID_FILE}")
            kill ${pid} 2>/dev/null
            sleep 2
            # Force kill if still running
            if ps -p ${pid} > /dev/null 2>&1; then
                kill -9 ${pid} 2>/dev/null
            fi
            rm -f "${PID_FILE}" 2>/dev/null
            
            # Start a new processor
            if ! start_processor; then
                log_message "Failed to restart processor after detecting it was stuck."
                consecutive_failures=$((consecutive_failures + 1))
            else
                consecutive_failures=0
                log_message "Successfully restarted processor after detecting it was stuck."
            fi
        else
            # Everything is working correctly
            consecutive_failures=0
            log_message "Processor is running and making progress."
        fi
        
        # Wait before next check
        log_message "Sleeping for ${CHECK_INTERVAL} seconds..."
        sleep ${CHECK_INTERVAL}
    done
}

# Run the main function
main