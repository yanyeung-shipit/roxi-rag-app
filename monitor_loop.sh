#!/bin/bash

# A simple monitor loop to check and restart the processor every 3 minutes
# This will keep running until the target percentage is reached

TARGET_PERCENTAGE=${1:-66.0}
CHECK_INTERVAL=${2:-180}  # 3 minutes by default

echo "Starting monitoring loop for processor with target ${TARGET_PERCENTAGE}%"
echo "Will check every ${CHECK_INTERVAL} seconds"
echo "Press Ctrl+C to stop"

# Run once immediately
./check_and_restart_processor.sh $TARGET_PERCENTAGE

# Then loop
while true; do
    # Check if target reached
    PROGRESS=$(./check_and_restart_processor.sh $TARGET_PERCENTAGE)
    if echo "$PROGRESS" | grep -q "TARGET REACHED"; then
        echo "Target reached! Exiting monitoring loop."
        break
    fi
    
    # Wait for next check
    echo "Sleeping for ${CHECK_INTERVAL} seconds..."
    sleep $CHECK_INTERVAL
done

echo "Monitoring complete."
