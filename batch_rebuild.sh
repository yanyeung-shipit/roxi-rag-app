#!/bin/bash

# Enhanced batch rebuild script with error handling and progress tracking
# This script continually processes chunks in small batches to avoid timeout issues

# Configuration - can be overridden via command line arguments
BATCH_SIZE=${1:-5}         # Number of chunks to process in one batch (default: 5)
DELAY_SECONDS=${2:-3}      # Delay between processing chunks (default: 3)
MAX_RUNTIME=${3:-7200}     # Maximum runtime in seconds (default: 2 hours)
LOG_FILE="logs/rebuild/batch_rebuild_$(date +%Y%m%d_%H%M%S).log"

# Create log directory if it doesn't exist
mkdir -p logs/rebuild

# Initialize counters
start_time=$(date +%s)
batch_count=0
success_count=0
error_count=0
last_chunk_id=0

# Log header
echo "Starting batch rebuild process at $(date)" | tee -a "$LOG_FILE"
echo "Configuration: BATCH_SIZE=$BATCH_SIZE, DELAY_SECONDS=$DELAY_SECONDS, MAX_RUNTIME=$MAX_RUNTIME" | tee -a "$LOG_FILE"
echo "-----------------------------------------" | tee -a "$LOG_FILE"

# Check initial progress
echo "Initial state:" | tee -a "$LOG_FILE"
python3 check_progress.py | tee -a "$LOG_FILE"
echo "-----------------------------------------" | tee -a "$LOG_FILE"

# Main processing loop
while true; do
    current_time=$(date +%s)
    elapsed=$((current_time - start_time))
    
    # Check if we've exceeded the maximum runtime
    if [ $elapsed -ge $MAX_RUNTIME ]; then
        echo "Maximum runtime of $MAX_RUNTIME seconds reached. Exiting." | tee -a "$LOG_FILE"
        break
    fi
    
    echo "Batch $((batch_count + 1)) started at $(date)" | tee -a "$LOG_FILE"
    
    # Process a batch of chunks
    for i in $(seq 1 $BATCH_SIZE); do
        # Check elapsed time for each chunk to ensure we don't exceed max runtime
        current_time=$(date +%s)
        elapsed=$((current_time - start_time))
        if [ $elapsed -ge $MAX_RUNTIME ]; then
            echo "Maximum runtime reached during batch. Exiting." | tee -a "$LOG_FILE"
            break 2  # Break out of both loops
        fi
        
        echo "Processing chunk $i of $BATCH_SIZE in batch $((batch_count + 1))..." | tee -a "$LOG_FILE"
        
        # Run the add_single_chunk.py script and capture its output and exit code
        output=$(python3 add_single_chunk.py 2>&1)
        exit_code=$?
        
        # Extract chunk ID from output if successful
        if [ $exit_code -eq 0 ]; then
            chunk_id=$(echo "$output" | grep -o "Processing chunk [0-9]* from document" | grep -o "[0-9]*" | head -1)
            if [ -n "$chunk_id" ]; then
                last_chunk_id=$chunk_id
                ((success_count++))
                echo "Successfully processed chunk ID: $chunk_id" | tee -a "$LOG_FILE"
            else
                echo "No more chunks to process. Exiting." | tee -a "$LOG_FILE"
                break 2  # Break out of both loops
            fi
        else
            ((error_count++))
            echo "Error processing chunk. Exit code: $exit_code" | tee -a "$LOG_FILE"
            echo "Error output: $output" | tee -a "$LOG_FILE"
        fi
        
        # Wait between chunks to avoid rate limits
        sleep $DELAY_SECONDS
    done
    
    # Increment batch counter
    ((batch_count++))
    
    # Check progress after each batch
    echo "Progress after batch $batch_count:" | tee -a "$LOG_FILE"
    python3 check_progress.py | tee -a "$LOG_FILE"
    echo "-----------------------------------------" | tee -a "$LOG_FILE"
    
    # Print stats
    echo "Stats after $batch_count batches:" | tee -a "$LOG_FILE"
    echo "Elapsed time: $elapsed seconds" | tee -a "$LOG_FILE"
    echo "Successful chunks: $success_count" | tee -a "$LOG_FILE"
    echo "Errors: $error_count" | tee -a "$LOG_FILE"
    echo "Last processed chunk ID: $last_chunk_id" | tee -a "$LOG_FILE"
    echo "-----------------------------------------" | tee -a "$LOG_FILE"
    
    # Wait between batches
    sleep $DELAY_SECONDS
done

# Final report
final_time=$(date +%s)
total_elapsed=$((final_time - start_time))
echo "Batch rebuild completed at $(date)" | tee -a "$LOG_FILE"
echo "Final stats:" | tee -a "$LOG_FILE"
echo "Total batches: $batch_count" | tee -a "$LOG_FILE"
echo "Total successful chunks: $success_count" | tee -a "$LOG_FILE"
echo "Total errors: $error_count" | tee -a "$LOG_FILE"
echo "Total runtime: $total_elapsed seconds" | tee -a "$LOG_FILE"
echo "-----------------------------------------" | tee -a "$LOG_FILE"

# Check final progress
echo "Final state:" | tee -a "$LOG_FILE"
python3 check_progress.py | tee -a "$LOG_FILE"