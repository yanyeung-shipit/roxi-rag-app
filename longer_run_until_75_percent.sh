#!/bin/bash

# This script is designed to run for an extended period, processing chunks
# until reaching 75% of the total chunks, with more aggressive batch sizes.

# Configuration
BATCH_SIZE=20     # Process 20 chunks at a time
TARGET_PCT=75.0   # Target percentage (75%)
LOG_DIR="logs"
TIMESTAMP=$(date "+%Y%m%d_%H%M%S")
LOG_FILE="${LOG_DIR}/process_75_percent_background_${TIMESTAMP}.log"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Write PID to file for monitoring
echo $$ > "process_75_percent.pid"

echo "Starting long-running processor to reach ${TARGET_PCT}% completion..." | tee -a "$LOG_FILE"
echo "Log file: $LOG_FILE" | tee -a "$LOG_FILE"
echo "Started at: $(date)" | tee -a "$LOG_FILE"
echo "Using batch size: $BATCH_SIZE" | tee -a "$LOG_FILE"

# Function to get current processing percentage
get_progress() {
    local vector_file="faiss_index.bin"
    local total_chunks=1261 # From previous analysis
    
    if [ -f "$vector_file" ]; then
        # Count processed chunks by checking for specific patterns in logs
        local processed_chunks=$(grep "Successfully processed chunk" "$LOG_FILE" | wc -l)
        
        # Add the initial chunks that were already processed
        local initial_chunks=65 # Based on recent log entry
        processed_chunks=$((processed_chunks + initial_chunks))
        
        # Calculate percentage
        local percentage=$(echo "scale=1; $processed_chunks * 100 / $total_chunks" | bc)
        echo "$percentage% ($processed_chunks/$total_chunks chunks)"
    else
        echo "0% (0/0 chunks) - Vector file not found"
    fi
}

# Run the Python script with customized parameters
python -u process_to_50_percent.py --batch-size=$BATCH_SIZE --target-percentage=$TARGET_PCT >> "$LOG_FILE" 2>&1

# Check final status
echo "Processor completed at: $(date)" | tee -a "$LOG_FILE"
echo "Final progress: $(get_progress)" | tee -a "$LOG_FILE"

# Clean up PID file
rm -f "process_75_percent.pid"