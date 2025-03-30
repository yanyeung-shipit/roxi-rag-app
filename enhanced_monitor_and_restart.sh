#!/bin/bash

# Enhanced Monitor and Restart Processing Script
# This script continuously monitors the progress of processing and restarts
# the process if it fails or stops, with improved database error detection.

# Configuration
CHECK_INTERVAL=300  # Check every 5 minutes
MAX_RETRIES=3       # Maximum number of consecutive retries before giving up
LOG_FILE="enhanced_monitoring.log"
MAX_RESTART_WAIT=15  # Maximum wait time between restart attempts (minutes)

# Define colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Log with timestamp
log_message() {
    local timestamp=$(date +'%Y-%m-%d %H:%M:%S')
    local message="$1"
    local level=${2:-"INFO"}
    
    case "$level" in
        "ERROR")
            echo -e "${timestamp} - ${RED}ERROR${NC} - $message" | tee -a "$LOG_FILE"
            ;;
        "WARNING")
            echo -e "${timestamp} - ${YELLOW}WARNING${NC} - $message" | tee -a "$LOG_FILE"
            ;;
        "SUCCESS")
            echo -e "${timestamp} - ${GREEN}SUCCESS${NC} - $message" | tee -a "$LOG_FILE"
            ;;
        *)
            echo -e "${timestamp} - ${BLUE}INFO${NC} - $message" | tee -a "$LOG_FILE"
            ;;
    esac
}

# Check current progress
get_current_progress() {
    local progress_output=$(python check_progress.py)
    local current_percentage=$(echo "$progress_output" | grep -o '[0-9]\+\.[0-9]\+%' | head -1 | sed 's/%//')
    
    # If no percentage found, default to 0
    if [ -z "$current_percentage" ]; then
        echo "0.0"
    else
        echo "$current_percentage"
    fi
}

# Check for database errors in logs
check_for_db_errors() {
    # Check for specific DB error signatures in logs
    if grep -q "SSL connection has been closed unexpectedly" "enhanced_process_to_50_percent.log" 2>/dev/null; then
        return 0  # Error found
    fi
    
    if grep -q "Can't reconnect until invalid transaction is rolled back" "enhanced_process_to_50_percent.log" 2>/dev/null; then
        return 0  # Error found
    fi
    
    if grep -q "OperationalError" "enhanced_process_to_50_percent.log" 2>/dev/null; then
        return 0  # Error found
    fi
    
    return 1  # No errors found
}

# Check if the target has been reached
is_target_reached() {
    local current_percentage=$1
    local target_percentage=${2:-50.0}
    
    # Compare with bc for floating point comparison
    if (( $(echo "$current_percentage >= $target_percentage" | bc -l) )); then
        return 0  # True, target reached
    else
        return 1  # False, target not reached
    fi
}

# Check if the processor is running
is_processor_running() {
    if pgrep -f "enhanced_process_to_50_percent.py" > /dev/null; then
        return 0  # True, processor is running
    fi
    
    # Check PID file
    if [ -f "enhanced_process.pid" ]; then
        pid=$(cat "enhanced_process.pid")
        if ps -p "$pid" > /dev/null; then
            return 0  # True, processor is running based on PID file
        else
            # PID file exists but process is not running, clean up
            log_message "PID file exists but process is not running. Cleaning up." "WARNING"
            rm -f "enhanced_process.pid"
        fi
    fi
    
    return 1  # False, processor is not running
}

# Clean up database locks and old processes
cleanup_before_restart() {
    log_message "Performing cleanup before restart..." "WARNING"
    
    # Kill any existing processes that might cause conflicts
    pkill -f "process_to_50_percent.py" 2>/dev/null
    pkill -f "batch_rebuild_to_target.py" 2>/dev/null
    
    # Wait for processes to terminate
    sleep 5
    
    # Remove any PID files
    rm -f "process_50_percent.pid" "enhanced_process.pid" 2>/dev/null
    
    # Optional: Run a quick Python script to ensure DB connection is reset
    python -c "
import sys
sys.path.append('.')
from app import db
try:
    db.session.rollback()
    print('Database session rolled back successfully')
except Exception as e:
    print(f'Error resetting database: {str(e)}')
" > enhanced_db_reset.log 2>&1
    
    log_message "Cleanup completed" "SUCCESS"
}

# Restart the processor
restart_processor() {
    local retry_count=$1
    
    # Calculate exponential backoff wait time (1min, 3min, 9min, 15min max)
    local wait_time=$((2 ** retry_count))
    if [ $wait_time -gt $MAX_RESTART_WAIT ]; then
        wait_time=$MAX_RESTART_WAIT
    fi
    
    log_message "Restarting enhanced processor (retry $retry_count)..." "WARNING"
    
    # Perform cleanup before restart
    cleanup_before_restart
    
    # Start the processor and save PID
    nohup python enhanced_process_to_50_percent.py >> "enhanced_process_to_50_percent.log" 2>&1 &
    local pid=$!
    echo $pid > "enhanced_process.pid"
    
    log_message "Started enhanced processor with PID: $pid" "SUCCESS"
    log_message "Waiting ${wait_time} minutes before next check..." "INFO"
    
    # Wait before next check (exponential backoff)
    sleep $((wait_time * 60))
}

# Main monitoring loop
main() {
    log_message "Starting enhanced monitoring process" "INFO"
    
    local retry_count=0
    local previous_percentage=0
    local stalled_count=0
    
    while true; do
        local current_percentage=$(get_current_progress)
        log_message "Current progress: ${current_percentage}%" "INFO"
        
        # Check if target reached
        if is_target_reached $current_percentage; then
            log_message "Target reached! Processing is complete (${current_percentage}%)" "SUCCESS"
            break
        fi
        
        # Check for database errors that would need immediate restart
        if check_for_db_errors; then
            log_message "Database errors detected in logs" "ERROR"
            restart_processor $retry_count
            retry_count=$((retry_count + 1))
            continue
        fi
        
        # Check if processor is running
        if is_processor_running; then
            log_message "Processor is running" "INFO"
            
            # Check if progress is stalled (same percentage for multiple checks)
            if (( $(echo "$current_percentage == $previous_percentage" | bc -l) )); then
                stalled_count=$((stalled_count + 1))
                if [ $stalled_count -ge 3 ]; then
                    log_message "Progress appears stalled at ${current_percentage}% for ${stalled_count} checks" "WARNING"
                    
                    # Find process and send SIGTERM to allow clean shutdown
                    local pid=$(cat "enhanced_process.pid" 2>/dev/null)
                    if [ -n "$pid" ] && ps -p "$pid" > /dev/null; then
                        log_message "Sending signal to PID $pid to allow clean shutdown" "WARNING"
                        kill -15 $pid 2>/dev/null
                        sleep 10  # Give it time to clean up
                    fi
                    
                    restart_processor $retry_count
                    retry_count=$((retry_count + 1))
                    stalled_count=0
                fi
            else
                # Progress changed, reset stall counter
                stalled_count=0
            fi
        else
            log_message "Processor is not running" "ERROR"
            restart_processor $retry_count
            retry_count=$((retry_count + 1))
        fi
        
        # Update previous percentage
        previous_percentage=$current_percentage
        
        # Give up after too many retries
        if [ $retry_count -ge $MAX_RETRIES ]; then
            log_message "Maximum retries ($MAX_RETRIES) reached. Manual intervention required." "ERROR"
            
            # Optional: Run simple version as a fallback
            log_message "Attempting to switch to simple processing mode..." "WARNING"
            pkill -f "enhanced_process_to_50_percent.py" 2>/dev/null
            nohup python continuous_rebuild.py >> "fallback_processing.log" 2>&1 &
            pid=$!
            echo $pid > "fallback_processor.pid"
            log_message "Started fallback processor with PID: $pid" "SUCCESS"
            break
        fi
        
        log_message "Sleeping for $CHECK_INTERVAL seconds before next check" "INFO"
        sleep $CHECK_INTERVAL
    done
}

# Set permissions to make executables
chmod +x check_progress.py 2>/dev/null
chmod +x enhanced_process_to_50_percent.py 2>/dev/null
chmod +x continuous_rebuild.py 2>/dev/null

# Run the main monitoring loop
main