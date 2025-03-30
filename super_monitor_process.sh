#!/bin/bash

# super_monitor_process.sh
# This script acts as a "supervisor" that checks both the monitor and processor
# and restarts them if they've stopped. It's designed to be extremely resilient
# to unexpected terminations.

# Set up log file
LOG_FILE="logs/super_monitor.log"
mkdir -p logs

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

restart_monitor() {
    log "Restarting enhanced monitor..."
    nohup ./enhanced_monitor.sh > /dev/null 2>&1 &
    MONITOR_PID=$!
    log "Enhanced monitor restarted with PID $MONITOR_PID"
    sleep 2 # Give it a moment to start
    
    # Verify it's running
    if ps -p $MONITOR_PID > /dev/null; then
        log "Monitor successfully restarted."
    else
        log "WARNING: Monitor failed to start. Will try again later."
    fi
}

check_monitor() {
    # Check if enhanced_monitor.sh is running
    if ! pgrep -f "enhanced_monitor.sh" > /dev/null; then
        log "Enhanced monitor not running. Restarting it."
        restart_monitor
    else
        log "Enhanced monitor is running."
    fi
}

check_processor() {
    # Check if processor is running via its PID file
    if [ -f "processor_66_percent.pid" ]; then
        PROCESSOR_PID=$(cat processor_66_percent.pid)
        if ! ps -p $PROCESSOR_PID > /dev/null; then
            log "Processor PID exists but process is not running. Letting monitor handle restart."
            # The enhanced monitor will detect this and restart the processor
            # We'll remove the stale PID file to help the monitor
            rm -f processor_66_percent.pid
            log "Removed stale PID file."
        else
            log "Processor is running with PID $PROCESSOR_PID."
        fi
    else
        log "No processor PID file found. Letting monitor handle start."
    fi
}

check_progress() {
    # Get current progress
    PROGRESS=$(python check_adaptive_processor.py --json | grep -o '"overall_percentage": [0-9.]*' | cut -d' ' -f2)
    TARGET=66.0
    
    log "Current progress: $PROGRESS%, Target: $TARGET%"
    
    # Check if target reached
    if (( $(echo "$PROGRESS >= $TARGET" | bc -l) )); then
        log "TARGET REACHED! Current: $PROGRESS%, Target: $TARGET%"
        log "Super monitor will exit now."
        exit 0
    fi
}

# Main monitoring loop
log "=== SUPER MONITOR STARTED ==="
log "This script will ensure both the processor and monitor stay running."
log "Target completion: 66.0%"

# Initial check and startup
check_monitor
check_processor

# Continue monitoring in a loop
while true; do
    log "--- Super Monitor Check ---"
    check_monitor
    check_processor
    check_progress
    
    log "Sleeping for 30 seconds..."
    sleep 30
done