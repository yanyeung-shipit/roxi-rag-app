#!/bin/bash

# Monitor and Restart Adaptive Processor
# This script continuously monitors the adaptive processor and restarts it if needed

# Configuration
LOG_FILE="logs/adaptive_processor_66_percent_monitor_$(date +%Y%m%d_%H%M%S).log"
PROCESSOR_NAME="adaptive_processor.py"
TARGET_PERCENTAGE=66.0
MAX_BATCH_SIZE=8  # Balanced batch size for memory-constrained environment
CHECK_INTERVAL=60  # seconds
MAX_RESTART_ATTEMPTS=10
PROCESSOR_LOG_FILE="logs/adaptive_processor_66_percent_$(date +%Y%m%d_%H%M%S).log"

# Create logs directory if it doesn't exist
mkdir -p logs

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

# Function to check if processor is running
is_running() {
    pgrep -f "$PROCESSOR_NAME.*--target $TARGET_PERCENTAGE" > /dev/null
    return $?
}

# Function to start the processor
start_processor() {
    log "${BLUE}Starting adaptive processor with target $TARGET_PERCENTAGE% and max batch size $MAX_BATCH_SIZE...${NC}"
    cd processors && nohup python adaptive_processor.py --target $TARGET_PERCENTAGE --max-batch $MAX_BATCH_SIZE > "../$PROCESSOR_LOG_FILE" 2>&1 &
    
    # Sleep briefly to let process start
    sleep 5
    
    # Check if started successfully
    if is_running; then
        pid=$(pgrep -f "$PROCESSOR_NAME.*--target $TARGET_PERCENTAGE")
        log "${GREEN}Processor started successfully with PID $pid${NC}"
        echo $pid > adaptive_processor_66_percent.pid
        log "${GREEN}PID saved to adaptive_processor_66_percent.pid${NC}"
        return 0
    else
        log "${RED}Failed to start processor!${NC}"
        return 1
    fi
}

# Print banner
log "===================================================================================="
log "                        ADAPTIVE PROCESSOR MONITOR                                  "
log "===================================================================================="
log "This script monitors the adaptive processor and restarts it if needed"
log "Target percentage: $TARGET_PERCENTAGE%"
log "Max batch size: $MAX_BATCH_SIZE"
log "Check interval: $CHECK_INTERVAL seconds"
log "Max restart attempts: $MAX_RESTART_ATTEMPTS"
log "Log file: $LOG_FILE"
log "===================================================================================="

# Main monitoring loop
restart_count=0

while true; do
    # Check if processor is running
    if ! is_running; then
        log "${YELLOW}Processor is not running.${NC}"
        
        # Check if we've exceeded the maximum restart attempts
        if [ $restart_count -ge $MAX_RESTART_ATTEMPTS ]; then
            log "${RED}Exceeded maximum restart attempts ($MAX_RESTART_ATTEMPTS).${NC}"
            log "${RED}Please check the system manually.${NC}"
            exit 1
        fi
        
        # Try to restart
        log "${YELLOW}Attempting restart ($((restart_count + 1))/$MAX_RESTART_ATTEMPTS)...${NC}"
        if start_processor; then
            restart_count=0  # Reset counter on successful restart
        else
            restart_count=$((restart_count + 1))
            log "${RED}Restart attempt $restart_count/$MAX_RESTART_ATTEMPTS failed.${NC}"
            # Wait longer after a failed restart
            sleep $((CHECK_INTERVAL * 2))
        fi
    else
        # Processor is running, check progress
        log "${GREEN}Processor is running with PID $(pgrep -f "$PROCESSOR_NAME.*--target $TARGET_PERCENTAGE")${NC}"
        
        # Check current progress (if check_processor_progress.py exists)
        if [ -f "check_processor_progress.py" ]; then
            log "${BLUE}Current progress:${NC}"
            python check_processor_progress.py --target $TARGET_PERCENTAGE | tail -10
            
            # Check if target reached
            current_progress=$(python check_processor_progress.py --json | grep -o '"percentage": [0-9.]*' | cut -d' ' -f2)
            if (( $(echo "$current_progress >= $TARGET_PERCENTAGE" | bc -l) )); then
                log "${GREEN}Target of $TARGET_PERCENTAGE% reached! Current progress: $current_progress%${NC}"
                log "${GREEN}Monitoring completed successfully.${NC}"
                exit 0
            else
                log "${BLUE}Progress: $current_progress% - Target: $TARGET_PERCENTAGE%${NC}"
            fi
        else
            log "${YELLOW}Unable to check progress: check_processor_progress.py not found${NC}"
        fi
        
        # Reset restart counter since processor is running
        restart_count=0
    fi
    
    # Wait before next check
    log "${BLUE}Sleeping for $CHECK_INTERVAL seconds...${NC}"
    sleep $CHECK_INTERVAL
done