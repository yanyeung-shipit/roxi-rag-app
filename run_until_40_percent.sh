#!/bin/bash
# This script runs the resilient processor until it reaches 40% completion
# It includes automatic restarts if the process exits prematurely

echo "Starting resilient processor at $(date)"
echo "Target: 40% completion"
echo "========================================"

mkdir -p logs

# Track whether we're done
DONE=0

while [ $DONE -eq 0 ]; do
    echo "Starting new processor run at $(date)"
    
    # Run the processor with a timeout to prevent hanging
    timeout 3600 python resilient_processor.py --target 40 --batch 1 --delay 3
    
    # Check exit status
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        echo "Processor completed successfully at $(date)"
        DONE=1
    elif [ $EXIT_CODE -eq 124 ]; then
        echo "Processor timed out after 1 hour at $(date)"
        echo "Restarting..."
        sleep 5
    else
        echo "Processor exited with code $EXIT_CODE at $(date)"
        echo "Restarting in 10 seconds..."
        sleep 10
    fi
    
    # Check progress using the percentage_complete field in the output
    PROGRESS=$(python check_progress.py --json | grep -o '"percentage_complete": [0-9.]*' | cut -d' ' -f2)
    
    echo "Current progress: $PROGRESS%"
    
    # If we've reached the target, exit
    if (( $(echo "$PROGRESS >= 40" | bc -l) )); then
        echo "Target reached! Progress is $PROGRESS%"
        DONE=1
    fi
done

echo "Processing completed at $(date)"
echo "Final progress: $(python check_progress.py --json | grep -o '"percentage_complete": [0-9.]*' | cut -d' ' -f2)%"