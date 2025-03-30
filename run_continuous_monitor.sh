#!/bin/bash

# Continuous Monitor for Processor
# This script runs the check_and_restart_processor.sh script every 5 minutes
# to ensure the processor stays running until the target percentage is reached

LOG_FILE="continuous_monitor.log"

echo "Starting continuous monitor at $(date)" | tee -a $LOG_FILE
echo "This will check and restart the processor every 5 minutes if needed" | tee -a $LOG_FILE
echo "=======================================" | tee -a $LOG_FILE

# Run the monitor indefinitely
while true; do
    echo "Running check at $(date)" | tee -a $LOG_FILE
    ./check_and_restart_processor.sh | tee -a $LOG_FILE
    
    # Check if we've reached the target
    if grep -q "Target reached" processor_monitor.log; then
        echo "Target completion detected! Monitoring complete at $(date)" | tee -a $LOG_FILE
        break
    fi
    
    echo "Sleeping for 5 minutes..." | tee -a $LOG_FILE
    sleep 300  # Sleep for 5 minutes
done

echo "Monitoring complete at $(date)" | tee -a $LOG_FILE