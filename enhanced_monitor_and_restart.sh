#!/bin/bash

# Enhanced Monitor and Restart Processor Script
# This script monitors the processor and restarts it if it stops
# It uses a very short check interval (20 seconds) to quickly restart the processor

TARGET_PERCENTAGE=${1:-66.0}
CHECK_INTERVAL=${2:-20}  # Check every 20 seconds by default
MONITOR_LOG_FILE="logs/monitor_66percent.log"
PROCESSOR_PID_FILE="processor_66_percent.pid"

# Kill any previously running monitors
pkill -f "enhanced_monitor_and_restart.sh" 2>/dev/null

# Create a PID file for this monitor
echo $$ > monitor_66percent.pid

echo "Starting enhanced monitoring for processor with target ${TARGET_PERCENTAGE}%"
echo "Checking every ${CHECK_INTERVAL} seconds"
echo "Monitor PID: $$"
echo "Monitor log: $MONITOR_LOG_FILE"

# Make sure the log directory exists
mkdir -p logs

# Main monitoring loop
while true; do
    echo "============================================================" >> $MONITOR_LOG_FILE
    
    # Get current completion percentage using the non-JSON output
    PROGRESS_INFO=$(python check_adaptive_processor.py --target $TARGET_PERCENTAGE 2>/dev/null | grep -E "^[0-9]+/[0-9]+ chunks \([0-9]+\.[0-9]+%\)$")
    CURRENT_PERCENTAGE=$(echo $PROGRESS_INFO | sed -E 's/.*\(([0-9]+\.[0-9]+)%\).*/\1/')
    
    if [ -z "$CURRENT_PERCENTAGE" ]; then
        CURRENT_PERCENTAGE="0.0"
    fi
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Current completion: ${CURRENT_PERCENTAGE}%" >> $MONITOR_LOG_FILE
    
    # Check if we've reached the target
    if (( $(echo "$CURRENT_PERCENTAGE >= $TARGET_PERCENTAGE" | bc -l) )); then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Processing complete! Target: ${TARGET_PERCENTAGE}%, Current: ${CURRENT_PERCENTAGE}%" >> $MONITOR_LOG_FILE
        break
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Still processing. Target: ${TARGET_PERCENTAGE}%, Current: ${CURRENT_PERCENTAGE}%" >> $MONITOR_LOG_FILE
    fi
    
    # Check if the processor is running
    if [ -f "$PROCESSOR_PID_FILE" ]; then
        PROCESSOR_PID=$(cat $PROCESSOR_PID_FILE)
        if ps -p $PROCESSOR_PID > /dev/null; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Processor running with PID $PROCESSOR_PID" >> $MONITOR_LOG_FILE
        else
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Process with PID $PROCESSOR_PID is not running, but PID file exists." >> $MONITOR_LOG_FILE
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Processor not running. Starting it now." >> $MONITOR_LOG_FILE
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting processor..." >> $MONITOR_LOG_FILE
            
            # Start the processor
            ./run_to_66_percent.sh
            
            # Sleep briefly to allow the processor to start
            sleep 5
        fi
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] No PID file found. Starting processor..." >> $MONITOR_LOG_FILE
        
        # Start the processor
        ./run_to_66_percent.sh
        
        # Sleep briefly to allow the processor to start
        sleep 5
    fi
    
    # Wait before checking again
    sleep $CHECK_INTERVAL
done

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Monitoring complete. Target percentage reached." >> $MONITOR_LOG_FILE
echo "Processor reached target of ${TARGET_PERCENTAGE}%"
