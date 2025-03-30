#!/bin/bash

# Monitor and auto-restart the simplified processor if it dies
# This script will check every 5 minutes if the processor is still running
# and restart it if needed

# Configuration
CHECK_INTERVAL=300  # 5 minutes in seconds
LOG_FILE="logs/monitor_$(date +%Y%m%d%H%M%S).log"

# Create log directory if it doesn't exist
mkdir -p logs

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

restart_processor() {
    log "Restarting processor..."
    ./run_in_background.sh >> "$LOG_FILE" 2>&1
    if [ $? -eq 0 ]; then
        log "Processor restarted successfully with PID $(cat processor.pid)"
    else
        log "Failed to restart processor"
    fi
}

check_processor() {
    if [ ! -f processor.pid ]; then
        log "No PID file found, starting processor"
        restart_processor
        return
    fi
    
    PID=$(cat processor.pid)
    if ! ps -p $PID > /dev/null; then
        log "Process $PID is not running, restarting"
        restart_processor
    else
        log "Process $PID is running normally"
    fi
}

log "Starting monitor script with check interval of $CHECK_INTERVAL seconds"

# Main monitoring loop
while true; do
    check_processor
    log "Next check in $CHECK_INTERVAL seconds"
    sleep $CHECK_INTERVAL
done