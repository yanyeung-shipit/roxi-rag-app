#!/bin/bash
# This script will persistently run the processing until we reach 75%
# It uses add_single_chunk.py, which is the most reliable processor

# Configuration
CHUNKS_PER_BATCH=5
TARGET_PERCENTAGE=75.0
MAX_ATTEMPTS=100
LOG_FILE="process_75_percent_background.log"

# Echo with timestamp function
timestamp() {
  date +"%Y-%m-%d %H:%M:%S"
}

echo "$(timestamp) Starting persistent chunk processing until $TARGET_PERCENTAGE% completion" >> $LOG_FILE
echo "Starting persistent processing until $TARGET_PERCENTAGE% completion"

attempts=0
current_percentage=0

# Function to get current percentage
get_current_percentage() {
  python check_progress.py | grep "complete" | tail -1 | awk '{print $2}' | tr -d '%'
}

# Initial percentage
current_percentage=$(get_current_percentage)
echo "$(timestamp) Starting at $current_percentage%" >> $LOG_FILE
echo "Starting at $current_percentage%"

# Process until target or max attempts
while [ "$(echo "$current_percentage < $TARGET_PERCENTAGE" | bc -l)" -eq 1 ] && [ $attempts -lt $MAX_ATTEMPTS ]; do
  # Increment attempts
  attempts=$((attempts + 1))
  
  echo "$(timestamp) Attempt $attempts: Processing $CHUNKS_PER_BATCH chunks" >> $LOG_FILE
  echo "Attempt $attempts: Processing $CHUNKS_PER_BATCH chunks"
  
  # Process chunks
  python add_single_chunk.py --max-chunks $CHUNKS_PER_BATCH >> $LOG_FILE 2>&1
  
  # Get new percentage
  current_percentage=$(get_current_percentage)
  
  echo "$(timestamp) Current progress: $current_percentage%" >> $LOG_FILE
  echo "Current progress: $current_percentage%"
  
  # Brief delay to allow system to stabilize
  sleep 3
done

# Final status
if [ "$(echo "$current_percentage >= $TARGET_PERCENTAGE" | bc -l)" -eq 1 ]; then
  echo "$(timestamp) Target reached! Final progress: $current_percentage%" >> $LOG_FILE
  echo "Target reached! Final progress: $current_percentage%"
else
  echo "$(timestamp) Maximum attempts reached. Final progress: $current_percentage%" >> $LOG_FILE
  echo "Maximum attempts reached. Final progress: $current_percentage%"
fi