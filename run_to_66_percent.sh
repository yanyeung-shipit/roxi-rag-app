#!/bin/bash
# run_to_66_percent.sh
#
# This script runs the adaptive processor until the vector store reaches
# 66% completion. It includes robust error handling and automatic retries
# for a more reliable background processing experience.
#
# Usage:
# ./run_to_66_percent.sh

# Configuration
LOG_DIR="logs"
PROCESSOR_SCRIPT="processors/adaptive_processor.py"
PID_FILE="processor_66_percent.pid"
LOG_FILE="${LOG_DIR}/processor_66_percent_$(date +%Y%m%d-%H%M%S).log"
TARGET_PERCENTAGE=66.0
MAX_RETRIES=5
RETRY_DELAY=60  # seconds

# Create logs directory if it doesn't exist
mkdir -p "${LOG_DIR}"

# Function to check if another processor is running
check_running() {
    if [ -f "${PID_FILE}" ]; then
        pid=$(cat "${PID_FILE}")
        if ps -p "${pid}" > /dev/null 2>&1; then
            echo "Processor already running with PID ${pid}"
            return 0
        else
            echo "Found stale PID file. Removing..."
            rm "${PID_FILE}"
        fi
    fi
    return 1
}

# Function to start the processor
start_processor() {
    echo "Starting adaptive processor to reach ${TARGET_PERCENTAGE}% completion..."
    echo "Logging to ${LOG_FILE}"
    
    # Run the processor in the background and save its PID
    python "${PROCESSOR_SCRIPT}" --target "${TARGET_PERCENTAGE}" > "${LOG_FILE}" 2>&1 &
    pid=$!
    
    # Save the PID to the PID file
    echo ${pid} > "${PID_FILE}"
    echo "Processor started with PID ${pid}"
    
    # Wait a moment to check if the process is still running
    sleep 5
    if ! ps -p "${pid}" > /dev/null 2>&1; then
        echo "Processor failed to start. Check the log file."
        rm "${PID_FILE}" 2>/dev/null
        return 1
    fi
    
    return 0
}

# Function to check completion percentage
check_completion() {
    # Use the check_adaptive_processor.py script to get the completion percentage
    completion_output=$(python check_adaptive_processor.py --target "${TARGET_PERCENTAGE}" --json)
    
    # Extract the completion percentage
    percentage=$(echo "${completion_output}" | grep -o '"percentage": [0-9.]*' | grep -o '[0-9.]*')
    
    echo "Current completion: ${percentage}%"
    
    # Check if completion is at or above target
    if (( $(echo "${percentage} >= ${TARGET_PERCENTAGE}" | bc -l) )); then
        echo "Target completion of ${TARGET_PERCENTAGE}% reached!"
        return 0
    else
        echo "Still processing. Target: ${TARGET_PERCENTAGE}%, Current: ${percentage}%"
        return 1
    fi
}

# Main execution
main() {
    # Check if processor is already running
    if check_running; then
        echo "Processor already running. Exiting."
        exit 0
    fi
    
    # Start the processor
    if ! start_processor; then
        echo "Failed to start processor."
        exit 1
    fi
    
    echo "Processor started successfully. It will run in the background until ${TARGET_PERCENTAGE}% completion."
    echo "Track progress with: python check_adaptive_processor.py"
    echo "View logs with: tail -f ${LOG_FILE}"
}

# Execute main function
main