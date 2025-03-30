#!/bin/bash

# Script to monitor the vector processing and create regular backups
# Run with: ./monitor_and_backup.sh

# Configure settings
BACKUP_INTERVAL=15  # minutes
CHECK_INTERVAL=5    # minutes
MAX_RUNTIME=86400   # 24 hours (in seconds)

# Directory for monitoring logs
LOG_DIR="./logs"
mkdir -p "$LOG_DIR"

# Log file
LOG_FILE="$LOG_DIR/monitor_$(date +%Y%m%d).log"

# Process ID file for the main processing script
PROCESSOR_PID_FILE=".processor.pid"

# Log with timestamp
log() {
  local message="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
  echo "$message" | tee -a "$LOG_FILE"
}

# Check if the processor is running
check_processor() {
  if [ -f "$PROCESSOR_PID_FILE" ]; then
    local pid=$(cat "$PROCESSOR_PID_FILE")
    if ps -p "$pid" > /dev/null; then
      echo "running"
      return 0
    fi
  fi
  echo "stopped"
  return 1
}

# Create a backup
create_backup() {
  log "Creating vector store backup..."
  if python backup_vector_store.py >> "$LOG_FILE" 2>&1; then
    log "Backup created successfully"
  else
    log "Failed to create backup"
  fi
}

# Check progress
check_progress() {
  local output=$(python check_progress.py --json 2>/dev/null)
  if [ $? -eq 0 ]; then
    local percentage=$(echo "$output" | grep -o '"percentage":[^,}]*' | cut -d':' -f2)
    local processed=$(echo "$output" | grep -o '"processed_chunks":[^,}]*' | cut -d':' -f2)
    local total=$(echo "$output" | grep -o '"total_chunks":[^,}]*' | cut -d':' -f2)
    
    # Format for consistent display
    if [ -n "$percentage" ] && [ -n "$processed" ] && [ -n "$total" ]; then
      log "Progress: ${percentage}% (${processed}/${total})"
    else
      log "Failed to parse progress information"
    fi
  else
    log "Failed to check progress"
  fi
}

# Check for target completion
check_target() {
  ./check_50_percent_progress.sh >> "$LOG_FILE" 2>&1
  if [ $? -eq 0 ]; then
    return 0  # Target reached
  else
    return 1  # Target not reached
  fi
}

# Main monitoring loop
main() {
  log "Starting vector store monitor and backup service"
  
  start_time=$(date +%s)
  next_backup_time=$((start_time + BACKUP_INTERVAL * 60))
  
  while true; do
    # Check if we've reached max runtime
    current_time=$(date +%s)
    runtime=$((current_time - start_time))
    if [ $runtime -ge $MAX_RUNTIME ]; then
      log "Maximum runtime reached. Performing final backup and exiting."
      create_backup
      exit 0
    fi
    
    # Check if the processor is running
    processor_status=$(check_processor)
    if [ "$processor_status" == "running" ]; then
      log "Processor is running"
    else
      log "Processor is not running"
    fi
    
    # Check progress
    check_progress
    
    # Check if we should create a backup
    if [ $current_time -ge $next_backup_time ]; then
      create_backup
      next_backup_time=$((current_time + BACKUP_INTERVAL * 60))
    fi
    
    # Check if target has been reached
    if check_target; then
      log "🎉 TARGET REACHED! Creating final backup and exiting."
      create_backup
      exit 0
    fi
    
    # Sleep until next check
    sleep $((CHECK_INTERVAL * 60))
  done
}

# Trap signals
trap 'log "Monitor interrupted. Creating final backup and exiting."; create_backup; exit 1' INT TERM

# Start the main loop
main