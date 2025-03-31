#!/bin/bash
# monitor_and_restart_processor_to_100_percent.sh
#
# This script monitors and restarts the 100% processor if it stops.
# It continues running until the target percentage is reached.
#
# Usage:
# ./monitor_and_restart_processor_to_100_percent.sh [batch_size] [check_interval]

# Default parameters
BATCH_SIZE=${1:-3}
CHECK_INTERVAL=${2:-60}
TARGET_PERCENTAGE=100.0

# Colors for better output
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Log file path
LOG_FILE="monitor_to_100percent.log"

# Function to log messages
log_message() {
    echo -e "$(date +'%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Function to check if the processor is running
is_processor_running() {
    pgrep -f "python.*enhanced_process_to_100_percent.py" > /dev/null
    return $?
}

# Function to get current progress
get_progress() {
    python check_progress.py --json | grep -o '"percentage": [0-9.]*' | cut -d' ' -f2
}

# Function to start the processor
start_processor() {
    log_message "${BLUE}Starting enhanced processor to 100% with batch size $BATCH_SIZE${NC}"
    nohup python enhanced_process_to_100_percent.py --batch-size $BATCH_SIZE > enhanced_100percent.log 2>&1 &
    sleep 5
    if is_processor_running; then
        log_message "${GREEN}Processor started successfully with PID $(pgrep -f 'python.*enhanced_process_to_100_percent.py')${NC}"
    else
        log_message "${RED}Failed to start processor!${NC}"
    fi
}

# Main monitoring loop
log_message "${BLUE}Starting enhanced monitor script for 100% target${NC}"
log_message "${BLUE}Initial progress: $(get_progress)%${NC}"

while true; do
    # Check if we've reached the target
    current_progress=$(get_progress)
    log_message "${GREEN}Current progress: ${current_progress}%${NC}"
    
    # If we've reached or exceeded 100%, exit
    if (( $(echo "$current_progress >= $TARGET_PERCENTAGE" | bc -l) )); then
        log_message "${GREEN}Target reached! Current progress: ${current_progress}%${NC}"
        log_message "${GREEN}Monitoring completed successfully.${NC}"
        exit 0
    fi
    
    # Check if the processor is running
    if ! is_processor_running; then
        log_message "${YELLOW}Processor not running. Restarting...${NC}"
        start_processor
    else
        log_message "${GREEN}Processor is running. All good.${NC}"
    fi
    
    # Wait before checking again
    sleep $CHECK_INTERVAL
done