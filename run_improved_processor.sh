#!/bin/bash
# Improved script for running the continuous processor
# This script manages timeouts and auto-restarts the processor periodically

# Configuration
BATCH_SIZE=5     # Number of chunks to process in each batch
MAX_BATCHES=5    # Number of batches to process in each run
TIMEOUT=300      # Maximum runtime in seconds before restarting (5 minutes)
SLEEP_TIME=10    # Time to sleep between runs in seconds
MAX_RUNS=100     # Maximum number of times to run the processor (set to -1 for infinite)
LOG_DIR="logs/continuous_processing"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Function to run the processor with timeout
run_processor() {
    local run_number=$1
    local log_file="$LOG_DIR/run_${run_number}_$(date +%Y%m%d_%H%M%S).log"
    
    echo "========================================================"
    echo "Starting processor run #$run_number at $(date)"
    echo "Processing $MAX_BATCHES batches with batch size $BATCH_SIZE"
    echo "Timeout: $TIMEOUT seconds"
    echo "Log file: $log_file"
    echo "========================================================"
    
    # Run the processor with timeout
    timeout $TIMEOUT python improved_continuous_processor.py --batch-size $BATCH_SIZE --max-batches $MAX_BATCHES 2>&1 | tee "$log_file"
    
    # Check the exit code
    local exit_code=${PIPESTATUS[0]}
    
    if [ $exit_code -eq 124 ]; then
        echo "Processor timed out after $TIMEOUT seconds"
    elif [ $exit_code -eq 0 ]; then
        echo "Processor completed successfully"
    else
        echo "Processor exited with code $exit_code"
    fi
    
    # Check progress
    python check_progress.py
    
    echo "Sleeping for $SLEEP_TIME seconds before next run..."
    sleep $SLEEP_TIME
    
    return $exit_code
}

# Main loop
run_count=1
while [ $MAX_RUNS -lt 0 ] || [ $run_count -le $MAX_RUNS ]; do
    run_processor $run_count
    
    # Increment the run counter
    run_count=$((run_count+1))
    
    # Check if we've reached the maximum number of runs
    if [ $MAX_RUNS -ge 0 ] && [ $run_count -gt $MAX_RUNS ]; then
        echo "Reached maximum number of runs ($MAX_RUNS). Exiting."
        break
    fi
done

# Final check of progress
echo "========================================================"
echo "Processing complete at $(date)"
echo "Total runs: $((run_count-1))"
echo "========================================================"
python check_progress.py