#!/bin/bash

# Script to monitor progress towards 50% and notify when target is reached
# This is designed to be run in the background or via cron

# Configuration
TARGET_PERCENTAGE=50.0
CHECK_INTERVAL=300  # Check every 5 minutes (300 seconds)
LOG_FILE="notify_50_percent.log"

# Log with timestamp
log_message() {
    echo "$(date +'%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Check if target has been reached
check_target_reached() {
    progress_output=$(python check_progress.py)
    current_percentage=$(echo "$progress_output" | grep -o '[0-9]\+\.[0-9]\+%' | head -1 | sed 's/%//')
    
    # If no percentage found, default to 0
    if [ -z "$current_percentage" ]; then
        current_percentage="0.0"
    fi
    
    log_message "Current progress: ${current_percentage}%"
    
    # Check if we've reached target
    if (( $(echo "$current_percentage >= $TARGET_PERCENTAGE" | bc -l) )); then
        return 0  # Target reached
    else
        return 1  # Target not reached yet
    fi
}

# Notify function - this can be expanded with additional notification methods
notify_target_reached() {
    # Create a notification file
    echo "$(date +'%Y-%m-%d %H:%M:%S') - TARGET REACHED: 50% processing complete" > "TARGET_50_PERCENT_REACHED.txt"
    
    # Print clear console notification
    clear
    echo "=================================================="
    echo "                 🎉 TARGET REACHED 🎉              "
    echo "  Processing has reached the 50% milestone!"
    echo "  $(date +'%Y-%m-%d %H:%M:%S')"
    echo "=================================================="
    
    # Log the milestone
    log_message "TARGET REACHED: Processing has reached 50% milestone!"
    
    # You could add additional notification methods here:
    # - Send email notification
    # - Trigger webhook
    # - Push notification, etc.
}

# Main monitoring loop
monitor_until_target() {
    log_message "Starting monitoring for 50% target"
    
    while true; do
        if check_target_reached; then
            notify_target_reached
            log_message "Notification sent, monitoring complete"
            break
        else
            log_message "Target not yet reached, checking again in ${CHECK_INTERVAL} seconds"
            sleep $CHECK_INTERVAL
        fi
    done
}

# Run in the background
if [ "$1" == "background" ]; then
    log_message "Starting background monitoring"
    nohup bash "$0" run > /dev/null 2>&1 &
    echo $! > "notify_monitor.pid"
    echo "Started background monitoring with PID: $(cat notify_monitor.pid)"
    exit 0
fi

# Run directly
if [ "$1" == "run" ]; then
    monitor_until_target
    exit 0
fi

# Default behavior - show usage
if [ -z "$1" ]; then
    echo "Usage: $0 [background|run|status]"
    echo "  background  - Start monitoring in the background"
    echo "  run         - Run monitoring in the foreground"
    echo "  status      - Check the status of background monitoring"
    exit 1
fi

# Check status
if [ "$1" == "status" ]; then
    if [ -f "notify_monitor.pid" ]; then
        pid=$(cat "notify_monitor.pid")
        if ps -p "$pid" > /dev/null; then
            echo "Monitoring is running with PID: $pid"
            echo "Current progress: $(python check_progress.py | grep -o '[0-9]\+\.[0-9]\+%' | head -1)"
        else
            echo "Monitoring is not running (stale PID file)"
        fi
    else
        echo "Monitoring is not running (no PID file found)"
    fi
    exit 0
fi

echo "Unknown command: $1"
echo "Usage: $0 [background|run|status]"
exit 1