#!/bin/bash

# Monitor and restart the processor if needed
# This script should be run in a loop with a sleep interval

# Configuration
CHECK_INTERVAL=60  # seconds between checks
LOG_FILE="monitor_and_restart.log"
RESTART_SCRIPT="./check_and_restart_processor.sh"
MAX_RETRIES=5      # Maximum number of restart attempts before cooling down
COOLDOWN_TIME=600  # seconds to wait after max retries before trying again

# Initialize counters
restart_attempts=0
last_restart_time=0

# Function to log messages with timestamps
log_message() {
    echo "$(date +'%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Function to check if we should restart based on retry count
should_restart() {
    current_time=$(date +%s)
    
    # If we've reached max retries, enforce a cooldown period
    if [ $restart_attempts -ge $MAX_RETRIES ]; then
        elapsed=$((current_time - last_restart_time))
        if [ $elapsed -lt $COOLDOWN_TIME ]; then
            log_message "In cooldown period. Waiting for $((COOLDOWN_TIME - elapsed)) more seconds before next attempt."
            return 1
        else
            # Reset counter after cooldown
            log_message "Cooldown period complete. Resetting retry counter."
            restart_attempts=0
        fi
    fi
    
    return 0
}

# Main monitoring loop
log_message "Starting processor monitoring service"

while true; do
    # Check if processor is running
    # If it needs restart and we're allowed to restart it, do so
    if should_restart; then
        log_message "Checking processor status..."
        if $RESTART_SCRIPT; then
            log_message "Restart script completed successfully"
            # If the processor was restarted, update counters
            # Check the PID file to see if it was actually restarted
            if [ -f "process_50_percent.pid" ]; then
                new_pid=$(cat process_50_percent.pid)
                if ps -p $new_pid > /dev/null; then
                    # Process is running with new PID
                    log_message "Processor running with PID $new_pid"
                    restart_attempts=0  # Reset counter on successful restart
                else
                    # PID file exists but process not running
                    last_restart_time=$(date +%s)
                    restart_attempts=$((restart_attempts + 1))
                    log_message "Restart failed. Attempt $restart_attempts of $MAX_RETRIES"
                fi
            else
                # No PID file, assume no restart was needed
                log_message "No PID file found. Processor might not need restart."
            fi
        else
            # Restart script failed
            last_restart_time=$(date +%s)
            restart_attempts=$((restart_attempts + 1))
            log_message "Restart script failed. Attempt $restart_attempts of $MAX_RETRIES"
        fi
    fi
    
    # Sleep until next check
    log_message "Sleeping for $CHECK_INTERVAL seconds until next check"
    sleep $CHECK_INTERVAL
done