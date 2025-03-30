#!/bin/bash

# Script to regularly check and log progress towards 50% target
# This script will run at specified intervals and record progress
# Run with: ./monitor_progress.sh

# Configure settings
CHECK_INTERVAL=300  # seconds (5 minutes)
LOG_FILE="progress_monitoring.log"
MAX_RUNTIME=86400   # 24 hours (in seconds)

# Import utility functions
source ./utils/bash_colors.sh 2>/dev/null || true

# Function to log progress
log_progress() {
  # Get current progress
  local result=$(python check_progress.py --json 2>/dev/null)
  
  # Check if the command succeeded
  if [ $? -ne 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ${RED}Failed to run progress check script${RESET}" | tee -a "$LOG_FILE"
    return 1
  fi
  
  # Extract progress information
  local current_percent=$(echo "$result" | grep -o '"percent_processed": [0-9.]*' | grep -o '[0-9.]*')
  local processed=$(echo "$result" | grep -o '"processed_chunks": [0-9]*' | grep -o '[0-9]*')
  local total=$(echo "$result" | grep -o '"total_chunks": [0-9]*' | grep -o '[0-9]*')
  
  # Format for display
  local formatted_percent=$(printf "%.2f%%" "$current_percent")
  
  # Log progress with timestamp
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Progress: $formatted_percent ($processed/$total chunks)" | tee -a "$LOG_FILE"
  
  # Check if we've reached 50%
  if (( $(echo "$current_percent >= 50.0" | bc -l) )); then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ${GREEN}🎉 Target of 50% has been reached!${RESET}" | tee -a "$LOG_FILE"
    return 0
  fi
  
  return 1
}

# Main monitoring loop
main() {
  echo "Starting progress monitoring. Checking every $CHECK_INTERVAL seconds." | tee -a "$LOG_FILE"
  echo "Results will be logged to: $LOG_FILE" | tee -a "$LOG_FILE"
  echo "----------------------------------------" | tee -a "$LOG_FILE"
  
  local start_time=$(date +%s)
  
  while true; do
    # Log current progress
    if log_progress; then
      echo "Target reached. Monitoring complete." | tee -a "$LOG_FILE"
      break
    fi
    
    # Check if we've exceeded max runtime
    local current_time=$(date +%s)
    local elapsed=$((current_time - start_time))
    
    if [ $elapsed -ge $MAX_RUNTIME ]; then
      echo "Maximum runtime of $(($MAX_RUNTIME / 3600)) hours reached. Stopping monitor." | tee -a "$LOG_FILE"
      break
    fi
    
    # Calculate remaining time if max runtime is set
    local remaining=$(($MAX_RUNTIME - $elapsed))
    echo "Monitoring for $(($remaining / 3600))h $(($remaining % 3600 / 60))m more. Next check in $CHECK_INTERVAL seconds." | tee -a "$LOG_FILE"
    
    # Sleep until next check
    sleep $CHECK_INTERVAL
  done
}

# Handle termination signals
trap 'echo "Monitor interrupted. Exiting." | tee -a "$LOG_FILE"; exit 1' INT TERM

# Start the main loop
main