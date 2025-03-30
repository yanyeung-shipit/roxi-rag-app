#!/bin/bash

# Simple script to check progress and restart processor if needed
# This script is designed to be run from cron or manually

TARGET_PERCENTAGE=${1:-66.0}
PROCESSOR_PID_FILE="processor_66_percent.pid"
LOG_FILE="logs/processor_restart_log.txt"

# Create logs directory if it doesn't exist
mkdir -p logs

echo "========================================" >> $LOG_FILE
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running processor check" >> $LOG_FILE

# Check if the processor is running
if [ -f "$PROCESSOR_PID_FILE" ]; then
    PROCESSOR_PID=$(cat $PROCESSOR_PID_FILE)
    if ps -p $PROCESSOR_PID > /dev/null; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Processor running with PID $PROCESSOR_PID" >> $LOG_FILE
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Process with PID $PROCESSOR_PID is not running, but PID file exists." >> $LOG_FILE
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Restarting processor..." >> $LOG_FILE
        
        # Start the processor
        ./run_to_66_percent.sh
        
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Processor restarted" >> $LOG_FILE
    fi
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] No PID file found. Starting processor..." >> $LOG_FILE
    
    # Start the processor
    ./run_to_66_percent.sh
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Processor started" >> $LOG_FILE
fi

# Get current progress
PROGRESS_OUTPUT=$(python check_adaptive_processor.py --target $TARGET_PERCENTAGE 2>&1)
CURRENT_PERCENTAGE=$(echo "$PROGRESS_OUTPUT" | grep -oE '[0-9]+/[0-9]+ chunks \([0-9]+\.[0-9]+%\)' | grep -oE '\([0-9]+\.[0-9]+%\)' | grep -oE '[0-9]+\.[0-9]+')

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Current progress: $CURRENT_PERCENTAGE%" >> $LOG_FILE
echo "Current progress: $CURRENT_PERCENTAGE%"

# Check if target reached
if (( $(echo "$CURRENT_PERCENTAGE >= $TARGET_PERCENTAGE" | bc -l) )); then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] TARGET REACHED! Current: $CURRENT_PERCENTAGE%, Target: $TARGET_PERCENTAGE%" >> $LOG_FILE
    echo "TARGET REACHED! Current: $CURRENT_PERCENTAGE%, Target: $TARGET_PERCENTAGE%"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Still processing. Target: $TARGET_PERCENTAGE%, Current: $CURRENT_PERCENTAGE%" >> $LOG_FILE
    echo "Still processing. Target: $TARGET_PERCENTAGE%, Current: $CURRENT_PERCENTAGE%"
    
    # Calculate remaining chunks
    TOTAL_CHUNKS=$(echo "$PROGRESS_OUTPUT" | grep -oE '[0-9]+/[0-9]+ chunks' | grep -oE '/[0-9]+' | grep -oE '[0-9]+')
    PROCESSED_CHUNKS=$(echo "$PROGRESS_OUTPUT" | grep -oE '[0-9]+/[0-9]+ chunks' | grep -oE '^[0-9]+' | grep -oE '[0-9]+')
    TARGET_CHUNKS=$(echo "$TOTAL_CHUNKS * $TARGET_PERCENTAGE / 100" | bc)
    REMAINING_CHUNKS=$(echo "$TARGET_CHUNKS - $PROCESSED_CHUNKS" | bc)
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Chunks remaining to reach target: $REMAINING_CHUNKS" >> $LOG_FILE
    echo "Chunks remaining to reach target: $REMAINING_CHUNKS"
fi
