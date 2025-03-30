#!/bin/bash

# ultra_conservative_scheduler.sh
#
# This script runs the single-chunk processor at regular intervals with cooling periods.
# It's designed to be extremely conservative with system resources.
#
# Usage:
# ./ultra_conservative_scheduler.sh
#
# To run in the background:
# nohup ./ultra_conservative_scheduler.sh > logs/scheduler.log 2>&1 &

# Configuration
LOG_DIR="logs"
SCHEDULER_LOG="${LOG_DIR}/scheduler.log"
PROCESSOR_SCRIPT="processors/single_chunk_processor.py"
TARGET_PERCENTAGE=66.0
COOLDOWN_PERIOD=30  # seconds to wait between chunk processing
PID_FILE="scheduler.pid"
MAX_RUNTIME=7200    # maximum runtime in seconds (2 hours)
MAX_FAILURES=5      # maximum consecutive failures

# Create logs directory if it doesn't exist
mkdir -p "${LOG_DIR}"

# Save our own PID
echo $$ > "${PID_FILE}"
trap 'rm -f ${PID_FILE}' EXIT

# Function to log messages
log_message() {
    local timestamp=$(date +'%Y-%m-%d %H:%M:%S')
    echo "[${timestamp}] $1" | tee -a "${SCHEDULER_LOG}"
}

# Function to get current progress
get_progress() {
    # Use check_adaptive_processor.py to get current progress
    python check_adaptive_processor.py --json | grep -o '"overall_percentage": [0-9.]*' | cut -d' ' -f2 || echo "0.0"
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

# Function to process a single chunk
process_single_chunk() {
    log_message "Processing a single chunk..."
    
    # Run the single-chunk processor
    python "${PROCESSOR_SCRIPT}" --target "${TARGET_PERCENTAGE}"
    
    # Check if the processor succeeded
    if [ $? -eq 0 ]; then
        log_message "Successfully processed a chunk."
        return 0
    else
        log_message "Failed to process a chunk."
        return 1
    fi
}

# Main function
main() {
    log_message "=== ULTRA CONSERVATIVE SCHEDULER STARTED ==="
    log_message "Target completion: ${TARGET_PERCENTAGE}%"
    log_message "Cooldown period: ${COOLDOWN_PERIOD} seconds"
    log_message "Maximum runtime: $(($MAX_RUNTIME / 60)) minutes"
    
    # Check if we've already reached the target
    if check_target_reached; then
        log_message "Target already reached! No need to run processor."
        exit 0
    fi
    
    # Initialize variables
    start_time=$(date +%s)
    consecutive_failures=0
    chunks_processed=0
    
    # Main processing loop
    while true; do
        # Check if we've exceeded the maximum runtime
        current_time=$(date +%s)
        runtime=$((current_time - start_time))
        
        if [ ${runtime} -gt ${MAX_RUNTIME} ]; then
            log_message "Maximum runtime of $(($MAX_RUNTIME / 60)) minutes exceeded. Exiting."
            exit 0
        fi
        
        # Check if we've reached the target
        if check_target_reached; then
            log_message "=== TARGET REACHED! SHUTTING DOWN SCHEDULER ==="
            exit 0
        fi
        
        # Process a single chunk
        if process_single_chunk; then
            consecutive_failures=0
            chunks_processed=$((chunks_processed + 1))
            log_message "Total chunks processed: ${chunks_processed}"
        else
            consecutive_failures=$((consecutive_failures + 1))
            log_message "Consecutive failures: ${consecutive_failures}"
            
            # If too many consecutive failures, exit
            if [ ${consecutive_failures} -ge ${MAX_FAILURES} ]; then
                log_message "Too many consecutive failures (${consecutive_failures}). Exiting."
                exit 1
            fi
            
            # Increase cooldown period for failures
            cooldown=$((COOLDOWN_PERIOD * consecutive_failures))
            log_message "Increasing cooldown to ${cooldown} seconds due to failures."
        fi
        
        # Calculate progress rate
        if [ ${chunks_processed} -gt 0 ]; then
            elapsed_minutes=$(echo "scale=2; ${runtime} / 60" | bc)
            rate=$(echo "scale=2; ${chunks_processed} / ${elapsed_minutes}" | bc)
            log_message "Processing rate: ${rate} chunks/minute"
            
            # Estimate time remaining
            current_progress=$(get_progress)
            if [ "$(echo "${current_progress} < ${TARGET_PERCENTAGE}" | bc -l)" -eq 1 ]; then
                progress_remaining=$(echo "${TARGET_PERCENTAGE} - ${current_progress}" | bc)
                chunks_remaining=$(echo "scale=0; (${progress_remaining} * 1261 / 100)" | bc)
                time_remaining_minutes=$(echo "scale=0; ${chunks_remaining} / ${rate}" | bc)
                
                if [ -n "${time_remaining_minutes}" ] && [ "${time_remaining_minutes}" != "0" ]; then
                    log_message "Estimated time remaining: ${time_remaining_minutes} minutes"
                fi
            fi
        fi
        
        # Wait before processing the next chunk
        log_message "Cooling down for ${COOLDOWN_PERIOD} seconds..."
        sleep ${COOLDOWN_PERIOD}
    done
}

# Run the main function
main