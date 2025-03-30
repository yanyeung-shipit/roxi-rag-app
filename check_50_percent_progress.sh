#!/bin/bash

# Script to check progress towards 50% completion target
# This provides a detailed report on the current state of processing

# Configuration
TARGET_PERCENTAGE=50.0
LOG_FILE="progress_check.log"
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Log with timestamp
log_message() {
    echo -e "$(date +'%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Format percentage with color based on value
format_percentage() {
    local value=$1
    local target=$2
    
    if (( $(echo "$value >= $target" | bc -l) )); then
        echo -e "${GREEN}${value}%${NC}"
    elif (( $(echo "$value >= ($target * 0.8)" | bc -l) )); then
        echo -e "${YELLOW}${value}%${NC}"
    else
        echo -e "${RED}${value}%${NC}"
    fi
}

# Get current progress
get_current_progress() {
    progress_output=$(python check_progress.py)
    current_percentage=$(echo "$progress_output" | grep -o '[0-9]\+\.[0-9]\+%' | head -1 | sed 's/%//')
    # If no percentage found, default to 0
    if [ -z "$current_percentage" ]; then
        current_percentage="0.0"
    fi
    echo "$current_percentage"
}

# Check if processor is running
is_processor_running() {
    # Check for batch processor
    if pid=$(pgrep -f "batch_rebuild_to_target.py" 2>/dev/null); then
        echo -e "${GREEN}Running (batch_rebuild_to_target.py, PID: $pid)${NC}"
        return
    fi
    
    # Check for incremental processor by process name
    if pid=$(pgrep -f "process_chunks_until_50_percent" 2>/dev/null); then
        echo -e "${GREEN}Running (process_chunks_until_50_percent.py, PID: $pid)${NC}"
        # Update PID file to stay in sync
        echo "$pid" > process_50_percent.pid
        return
    fi
    
    # Check as a fallback using the PID file
    if [ -f "process_50_percent.pid" ]; then
        pid=$(cat "process_50_percent.pid")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo -e "${GREEN}Running (PID: $pid)${NC}"
            return
        fi
    fi
    
    # No processor is running
    echo -e "${RED}Not running${NC}"
}

# Get estimated time remaining based on current progress
get_time_estimate() {
    current=$1
    
    # If we're already at target, no time remaining
    if (( $(echo "$current >= $TARGET_PERCENTAGE" | bc -l) )); then
        echo "Complete"
        return
    fi
    
    # Check for progress log to estimate time
    if [ -f "$LOG_FILE" ]; then
        # Get timestamp of last progress point
        last_timestamp=$(grep -o '[0-9]\+-[0-9]\+-[0-9]\+ [0-9]\+:[0-9]\+:[0-9]\+' "$LOG_FILE" | tail -1)
        last_progress=$(grep "Current progress:" "$LOG_FILE" | tail -1 | grep -o '[0-9]\+\.[0-9]\+%' | sed 's/%//')
        
        if [ -n "$last_timestamp" ] && [ -n "$last_progress" ]; then
            # Calculate time difference in seconds
            last_time=$(date -d "$last_timestamp" +%s)
            current_time=$(date +%s)
            time_diff=$((current_time - last_time))
            
            # If we have meaningful time difference and progress difference
            if [ $time_diff -gt 0 ] && (( $(echo "$current > $last_progress" | bc -l) )); then
                # Calculate progress per second
                progress_diff=$(echo "$current - $last_progress" | bc -l)
                progress_per_second=$(echo "$progress_diff / $time_diff" | bc -l)
                
                # Calculate estimated remaining time
                remaining_progress=$(echo "$TARGET_PERCENTAGE - $current" | bc -l)
                if (( $(echo "$progress_per_second > 0" | bc -l) )); then
                    seconds_remaining=$(echo "$remaining_progress / $progress_per_second" | bc -l)
                    seconds_remaining=${seconds_remaining%.*}
                    
                    # Format time nicely
                    if [ $seconds_remaining -gt 3600 ]; then
                        hours=$((seconds_remaining / 3600))
                        minutes=$(((seconds_remaining % 3600) / 60))
                        echo "~${hours}h ${minutes}m"
                    elif [ $seconds_remaining -gt 60 ]; then
                        minutes=$((seconds_remaining / 60))
                        seconds=$((seconds_remaining % 60))
                        echo "~${minutes}m ${seconds}s"
                    else
                        echo "~${seconds_remaining}s"
                    fi
                    return
                fi
            fi
        fi
    fi
    
    echo "Calculating..."
}

# Main function
main() {
    echo -e "${BLUE}=== Progress Report ====${NC}"
    
    # Get current progress
    current=$(get_current_progress)
    formatted_progress=$(format_percentage $current $TARGET_PERCENTAGE)
    
    echo -e "Current progress: $formatted_progress"
    echo -e "Target: ${TARGET_PERCENTAGE}%"
    echo -e "Processor status: $(is_processor_running)"
    echo -e "Estimated time to target: $(get_time_estimate $current)"
    
    # Add additional system information
    echo -e "\n${BLUE}=== System Information ====${NC}"
    echo -e "Memory usage: $(free -m | awk 'NR==2{printf "%.1f/%.1f MB (%.1f%%)", $3,$2,$3*100/$2}')"
    echo -e "CPU load: $(uptime | awk -F'[a-z]:' '{ print $2}')"
    
    # If target reached, display completion message
    if (( $(echo "$current >= $TARGET_PERCENTAGE" | bc -l) )); then
        echo -e "\n${GREEN}Target reached! Processing is complete.${NC}"
    fi
}

# Run the main function and save output to log
main | tee -a "$LOG_FILE"