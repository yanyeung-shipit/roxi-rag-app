#!/bin/bash
# Enhanced Monitor and Restart Script for ROXI
#
# This script monitors a processor script and restarts it if it fails or stops
# running. It also provides more robust error handling and logging.
#
# Usage: ./enhanced_monitor_and_restart.sh [script_to_monitor] [args...]
#
# Example: ./enhanced_monitor_and_restart.sh enhanced_process_to_50_percent.py
#
# Features:
# - Detailed logging with timestamps
# - Exponential backoff for restart attempts
# - Maximum restart limit to prevent excessive restarts
# - Graceful shutdown capability via SIGINT
# - Progress reporting
# - Email notifications (if configured)

# Configuration
MAX_RESTARTS=10                   # Maximum number of restart attempts
LOG_FILE="monitor_restart.log"    # Log file name
BACKOFF_BASE=30                   # Base delay in seconds between restart attempts
PROGRESS_CHECK_INTERVAL=300       # Check progress every 5 minutes
NOTIFICATION_EMAIL=""             # Set to an email to enable notifications

# File to store PID of the monitor
MONITOR_PID_FILE="monitor.pid"

# Initialize variables
restart_count=0
last_progress=0
next_backoff=$BACKOFF_BASE
script_to_run=""
script_args=""

# Handle command-line arguments
if [ $# -eq 0 ]; then
    echo "Error: No script specified to monitor"
    echo "Usage: $0 [script_to_monitor] [args...]"
    exit 1
fi

script_to_run="$1"
shift
script_args="$@"

# Create log file if it doesn't exist
touch "$LOG_FILE"

# Function to log messages
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Function to send notification (if configured)
send_notification() {
    if [ -n "$NOTIFICATION_EMAIL" ]; then
        echo "$1" | mail -s "ROXI Processor Notification" "$NOTIFICATION_EMAIL"
    fi
}

# Function to clean up when script exits
cleanup() {
    log_message "Monitor stopping, cleaning up..."
    
    # Kill the monitored process if it's still running
    if [ -n "$pid" ] && ps -p $pid > /dev/null; then
        log_message "Terminating monitored process (PID: $pid)"
        kill -15 $pid 2>/dev/null
        
        # Give it a moment to terminate gracefully
        sleep 2
        
        # Force kill if still running
        if ps -p $pid > /dev/null; then
            log_message "Process didn't terminate gracefully, forcing termination"
            kill -9 $pid 2>/dev/null
        fi
    fi
    
    # Clean up PID file
    if [ -f "$MONITOR_PID_FILE" ]; then
        rm "$MONITOR_PID_FILE"
    fi
    
    log_message "Monitor shutdown complete"
    exit 0
}

# Set up trap to handle termination signals
trap cleanup SIGINT SIGTERM

# Create PID file
echo $$ > "$MONITOR_PID_FILE"
log_message "Monitor started with PID $$, monitoring: $script_to_run $script_args"

# Check if the script exists and is executable
if [ ! -f "$script_to_run" ]; then
    log_message "Error: Script '$script_to_run' not found"
    exit 1
fi

if [ ! -x "$script_to_run" ]; then
    log_message "Warning: Script '$script_to_run' is not executable, attempting to make it executable"
    chmod +x "$script_to_run"
    
    if [ $? -ne 0 ]; then
        log_message "Error: Failed to make script executable"
        exit 1
    fi
fi

# Initial notification
log_message "Starting monitoring of $script_to_run"
send_notification "ROXI processor monitoring started for $script_to_run"

# Function to check processing progress
check_progress() {
    progress_report=$(python check_progress.py 2>/dev/null)
    current_progress=$(echo "$progress_report" | grep "Percentage completed" | grep -o '[0-9.]*')
    
    if [ -z "$current_progress" ]; then
        log_message "Warning: Couldn't retrieve current progress"
        return
    fi
    
    if [ $(echo "$current_progress > $last_progress" | bc -l) -eq 1 ]; then
        log_message "Progress update: $current_progress% (increased from $last_progress%)"
        last_progress=$current_progress
    elif [ $(echo "$current_progress < $last_progress" | bc -l) -eq 1 ]; then
        log_message "Warning: Progress decreased from $last_progress% to $current_progress%"
        last_progress=$current_progress
    fi
}

# Main monitoring loop
last_progress_check=$(date +%s)

while [ $restart_count -lt $MAX_RESTARTS ]; do
    log_message "Starting $script_to_run (attempt $((restart_count + 1))/$MAX_RESTARTS)"
    
    # Start the process
    python $script_to_run $script_args &
    pid=$!
    
    log_message "Process started with PID: $pid"
    
    # Wait for process to finish
    while kill -0 $pid 2>/dev/null; do
        # Check if it's time to check progress
        current_time=$(date +%s)
        if [ $((current_time - last_progress_check)) -ge $PROGRESS_CHECK_INTERVAL ]; then
            check_progress
            last_progress_check=$current_time
        fi
        
        # Sleep before checking again
        sleep 10
    done
    
    # Process terminated
    wait $pid
    exit_code=$?
    
    # Check exit code
    if [ $exit_code -eq 0 ]; then
        log_message "Process completed successfully with exit code 0"
        send_notification "ROXI processor $script_to_run completed successfully"
        # Clean up and exit
        cleanup
        exit 0
    else
        log_message "Process failed with exit code $exit_code"
        
        # Increment restart count
        restart_count=$((restart_count + 1))
        
        # Check if we've hit the max restarts
        if [ $restart_count -ge $MAX_RESTARTS ]; then
            log_message "Maximum restart attempts ($MAX_RESTARTS) reached. Giving up."
            send_notification "ROXI processor $script_to_run failed after $MAX_RESTARTS attempts. Manual intervention required."
            break
        fi
        
        # Exponential backoff
        log_message "Waiting $next_backoff seconds before restarting..."
        sleep $next_backoff
        next_backoff=$((next_backoff * 2))
        
        # Cap the backoff at 1 hour
        if [ $next_backoff -gt 3600 ]; then
            next_backoff=3600
        fi
    fi
done

log_message "Monitor exiting after $restart_count restart attempts"
cleanup