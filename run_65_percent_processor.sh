#!/usr/bin/env bash
# run_65_percent_processor.sh
# Script to run and monitor the 65% processor service
# This script includes better error handling and monitoring

# Set strict mode
set -euo pipefail

# Constants
LOG_FILE="process_to_65_percent_service.log"
PID_FILE="process_to_65_percent.pid"
BATCH_SIZE=5
TARGET_PERCENTAGE=65.0
MAX_RESTART_ATTEMPTS=3
CHECK_INTERVAL=15  # seconds

# Terminal colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Ensure log directory exists
mkdir -p logs

# Function to log messages
log() {
  echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Function to check if the process is running
is_running() {
  if [ -f "$PID_FILE" ]; then
    local pid=$(cat "$PID_FILE")
    if ps -p "$pid" >/dev/null; then
      return 0  # Process is running
    fi
  fi
  return 1  # Process is not running
}

# Function to gracefully stop the process
stop_process() {
  if [ -f "$PID_FILE" ]; then
    local pid=$(cat "$PID_FILE")
    log "${YELLOW}Stopping processor with PID $pid...${NC}"
    
    # Send SIGTERM for graceful shutdown
    if ps -p "$pid" >/dev/null; then
      kill -15 "$pid" 2>/dev/null || true
      
      # Wait for process to exit
      local wait_count=0
      while ps -p "$pid" >/dev/null && [ $wait_count -lt 10 ]; do
        sleep 1
        wait_count=$((wait_count + 1))
      done
      
      # Force kill if still running
      if ps -p "$pid" >/dev/null; then
        log "${RED}Process did not exit gracefully, force killing...${NC}"
        kill -9 "$pid" 2>/dev/null || true
      else
        log "${GREEN}Process exited gracefully${NC}"
      fi
    else
      log "${YELLOW}Process was not running, cleaning up PID file${NC}"
    fi
    
    # Clean up PID file regardless
    rm -f "$PID_FILE"
  else
    log "${YELLOW}No PID file found, process may not be running${NC}"
  fi
}

# Function to start the 65% processor
start_process() {
  log "${GREEN}Starting 65% processor with batch size $BATCH_SIZE and target $TARGET_PERCENTAGE%${NC}"
  
  # Stop any existing process
  stop_process
  
  # Start the processor
  nohup python3 process_to_65_percent_service.py --batch-size "$BATCH_SIZE" --target "$TARGET_PERCENTAGE" >> "$LOG_FILE" 2>&1 &
  
  # Check if started successfully
  sleep 2
  if is_running; then
    local pid=$(cat "$PID_FILE")
    log "${GREEN}Processor started successfully with PID $pid${NC}"
    return 0
  else
    log "${RED}Failed to start processor${NC}"
    return 1
  fi
}

# Function to monitor the processor
monitor_process() {
  local restart_count=0
  
  while [ $restart_count -lt $MAX_RESTART_ATTEMPTS ]; do
    if ! is_running; then
      log "${YELLOW}Processor is not running, attempting restart ($((restart_count + 1))/$MAX_RESTART_ATTEMPTS)${NC}"
      if start_process; then
        restart_count=0  # Reset counter on successful restart
      else
        restart_count=$((restart_count + 1))
        log "${RED}Restart attempt $restart_count/$MAX_RESTART_ATTEMPTS failed${NC}"
        sleep $((CHECK_INTERVAL * 2))  # Wait longer after failed restart
      fi
    else
      # Check progress
      log "${BLUE}Processor is running, checking progress...${NC}"
      python3 check_processor_progress.py
      
      # Check if target reached
      if python3 check_processor_progress.py --json | grep -q '"percentage": \(6[5-9]\|[7-9][0-9]\|100\)\.'; then
        log "${GREEN}Target percentage reached, processing complete!${NC}"
        break
      fi
    fi
    
    # Wait before next check
    sleep $CHECK_INTERVAL
  done
  
  if [ $restart_count -ge $MAX_RESTART_ATTEMPTS ]; then
    log "${RED}Exceeded maximum restart attempts ($MAX_RESTART_ATTEMPTS), giving up${NC}"
    return 1
  fi
  
  return 0
}

# Main function
main() {
  log "${BLUE}=== Starting 65% Processor Monitoring Script ===${NC}"
  
  # Handle script termination
  trap 'log "${YELLOW}Script interrupted, stopping processor...${NC}"; stop_process; exit 0' INT TERM
  
  # Start the processor
  start_process || { log "${RED}Initial start failed, exiting${NC}"; exit 1; }
  
  # Monitor the processor
  monitor_process
  
  log "${GREEN}=== 65% Processor Monitoring Script Completed ===${NC}"
}

# Run the main function
main "$@"