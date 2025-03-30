#!/bin/bash
# This script will run the batch rebuild process until it completes or reaches 66% completion

# Create logs directory if it doesn't exist
mkdir -p logs/batch_processing

timestamp=$(date +%Y%m%d_%H%M%S)
log_file="logs/batch_processing/batch_rebuild_${timestamp}.log"
echo "Starting continuous batch rebuild to reach 66% completion..."
echo "Log file: ${log_file}"

# Maximum number of attempts
max_attempts=10
attempt=1

while [ $attempt -le $max_attempts ]; do
    echo "Attempt $attempt of $max_attempts"
    
    # Run the process with batch size 5
    python process_to_sixty_six_percent.py --batch-size 5 >> ${log_file} 2>&1
    
    # Check if the target has been reached
    progress=$(python check_progress.py | grep "complete" | awk '{print $2}' | tr -d '%')
    
    echo "Current progress: ${progress}%"
    
    # Check if we've reached or exceeded the target
    if (( $(echo "$progress >= 66.0" | bc -l) )); then
        echo "Target of 66% reached! Final progress: ${progress}%"
        break
    fi
    
    echo "Taking a short break before the next attempt..."
    sleep 3
    
    # Increment attempt counter
    ((attempt++))
done

if [ $attempt -gt $max_attempts ]; then
    echo "Maximum attempts reached. Final progress: ${progress}%"
fi

echo "Process completed. Check log file for details: ${log_file}"