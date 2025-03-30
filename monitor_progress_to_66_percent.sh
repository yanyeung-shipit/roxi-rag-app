#!/bin/bash

# Configuration
LOG_DIR="logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/monitor_progress_to_66_percent_$TIMESTAMP.log"
TARGET_PERCENTAGE=66.0
CHECK_INTERVAL=60  # seconds

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Color codes for better readability
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to log with timestamp
log() {
    echo -e "$(date +'%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Print banner
log "===================================================================================="
log "                   MONITOR PROGRESS TO 66% TARGET                                   "
log "===================================================================================="
log "This script monitors progress toward the 66% target without restarting the processor"
log "Target percentage: $TARGET_PERCENTAGE%"
log "Check interval: $CHECK_INTERVAL seconds"
log "Log file: $LOG_FILE"
log "===================================================================================="

# Function to check if processor is running
is_running() {
    pgrep -f "adaptive_processor.py.*--target $TARGET_PERCENTAGE" > /dev/null
    return $?
}

# Make sure we're in the project root directory
cd "$(dirname "$0")" || exit 1

# Function to get current progress percentage
get_progress() {
    if [ -f "check_processor_progress.py" ]; then
        PROGRESS=$(python check_processor_progress.py --json | grep -o '"percentage": [0-9.]*' | cut -d' ' -f2)
        echo "$PROGRESS"
    else
        echo "0.0"  # Default if can't check progress
    fi
}

# Function to get time estimate to completion
get_time_estimate() {
    if [ -f "check_processor_progress.py" ]; then
        CURRENT=$(get_progress)
        REMAINING=$(echo "$TARGET_PERCENTAGE - $CURRENT" | bc)
        PROCESSED=$(python check_processor_progress.py --json | grep -o '"processed_chunks": [0-9]*' | cut -d' ' -f2)
        TOTAL=$(python check_processor_progress.py --json | grep -o '"total_chunks": [0-9]*' | cut -d' ' -f2)
        NEEDED=$(echo "($TARGET_PERCENTAGE * $TOTAL / 100) - $PROCESSED" | bc)
        
        # Get processing rate (chunks per minute)
        RATE=$(python check_processor_progress.py --json | grep -o '"rate_per_minute": [0-9.]*' | cut -d' ' -f2)
        
        if (( $(echo "$RATE > 0" | bc -l) )); then
            # Calculate estimated minutes remaining
            MINUTES=$(echo "$NEEDED / $RATE" | bc -l)
            # Round to 1 decimal place
            MINUTES=$(printf "%.1f" $MINUTES)
            echo "$MINUTES minutes"
        else
            echo "Unknown (can't determine rate)"
        fi
    else
        echo "Unknown (can't check progress)"
    fi
}

# Function to get processor resources
get_resources() {
    if [ -f "processors/adaptive_processor.py" ]; then
        # Get PID
        PID=$(pgrep -f "adaptive_processor.py.*--target $TARGET_PERCENTAGE")
        if [ -n "$PID" ]; then
            # Get CPU and memory usage
            CPU=$(ps -p $PID -o %cpu | tail -1 | tr -d ' ')
            MEM=$(ps -p $PID -o %mem | tail -1 | tr -d ' ')
            echo "CPU: $CPU%, Memory: $MEM%"
        else
            echo "Process not found"
        fi
    else
        echo "Unknown (can't find processor)"
    fi
}

# Main monitoring loop
while true; do
    # Check if processor is running
    if is_running; then
        PROGRESS=$(get_progress)
        TIME_ESTIMATE=$(get_time_estimate)
        RESOURCES=$(get_resources)
        
        log "${GREEN}Processor is running${NC}"
        log "${BLUE}Progress: $PROGRESS% - Target: $TARGET_PERCENTAGE%${NC}"
        log "${BLUE}Estimated time remaining: $TIME_ESTIMATE${NC}"
        log "${BLUE}Resource usage: $RESOURCES${NC}"
        
        # Check if target reached
        if (( $(echo "$PROGRESS >= $TARGET_PERCENTAGE" | bc -l) )); then
            log "${GREEN}Target of $TARGET_PERCENTAGE% reached! Current progress: $PROGRESS%${NC}"
            log "${GREEN}Monitoring completed successfully.${NC}"
            exit 0
        fi
    else
        log "${YELLOW}Processor is not running.${NC}"
        
        # Check if target already reached
        PROGRESS=$(get_progress)
        if (( $(echo "$PROGRESS >= $TARGET_PERCENTAGE" | bc -l) )); then
            log "${GREEN}Target of $TARGET_PERCENTAGE% already reached! Current progress: $PROGRESS%${NC}"
            log "${GREEN}Monitoring completed successfully.${NC}"
            exit 0
        else
            log "${YELLOW}Progress: $PROGRESS% - Target: $TARGET_PERCENTAGE%${NC}"
            log "${YELLOW}Processor not running and target not reached.${NC}"
        fi
    fi
    
    # Wait before next check
    log "${BLUE}Sleeping for $CHECK_INTERVAL seconds...${NC}"
    sleep $CHECK_INTERVAL
done