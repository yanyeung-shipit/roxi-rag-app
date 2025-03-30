#!/bin/bash

# Script to monitor and automatically restart the processing script if it fails
# This ensures continuous processing even if there are temporary errors
# Run with: ./monitor_and_restart.sh

# Configure settings
MAX_RETRIES=10
CHECK_INTERVAL=60  # seconds
PROCESSOR_SCRIPT="process_chunks_until_50_percent.py"
LOG_FILE="continuous_processing.log"
PID_FILE=".processor.pid"

# Log with timestamp
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Start the processor
start_processor() {
  log "Starting processor: $PROCESSOR_SCRIPT"
  python "$PROCESSOR_SCRIPT" >> "$LOG_FILE" 2>&1 &
  
  # Save PID
  PID=$!
  echo $PID > "$PID_FILE"
  log "Processor started with PID: $PID"
  
  # Wait for startup
  sleep 5
  
  # Verify process is running
  if ps -p $PID > /dev/null; then
    log "Processor started successfully"
    return 0
  else
    log "Failed to start processor"
    return 1
  fi
}

# Check if processor is running
check_processor() {
  if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p $PID > /dev/null; then
      log "Processor is running (PID: $PID)"
      return 0
    else
      log "Processor not running (PID: $PID)"
      rm -f "$PID_FILE"
      return 1
    fi
  else
    log "No PID file found"
    return 1
  fi
}

# Check if we've reached 50%
check_completion() {
  # Run the check script silently and get its exit code
  ./check_50_percent_progress.sh > /dev/null 2>&1
  return $?
}

# Main monitoring loop
main() {
  log "Starting processor monitor"
  
  retries=0
  
  while [ $retries -lt $MAX_RETRIES ]; do
    # Check if target reached
    if check_completion; then
      log "🎉 Target of 50% has been reached! Monitoring complete."
      exit 0
    fi
    
    # Check if processor is running
    if ! check_processor; then
      retries=$((retries + 1))
      log "Processor not running. Attempt $retries of $MAX_RETRIES"
      
      # Create backup before restarting
      log "Creating backup before restart..."
      python backup_vector_store.py >> "$LOG_FILE" 2>&1
      
      # Restart processor
      if start_processor; then
        log "Processor restarted successfully"
        retries=0  # Reset retry counter on successful restart
      else
        log "Failed to restart processor"
        sleep $((CHECK_INTERVAL * 2))  # Wait longer after failure
      fi
    fi
    
    # Sleep before next check
    sleep $CHECK_INTERVAL
  done
  
  log "Maximum retries reached. Monitoring stopped."
  exit 1
}

# Handle termination signals
trap 'log "Monitor interrupted. Exiting."; exit 1' INT TERM

# Start the main loop
main