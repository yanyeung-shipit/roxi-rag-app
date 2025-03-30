#!/bin/bash

# Configuration
LOG_DIR="logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/processor_66_percent_$TIMESTAMP.log"
PROCESSOR_NAME="adaptive_processor.py"
TARGET_PERCENTAGE=66.0
MAX_BATCH_SIZE=8  # Balanced batch size for memory-constrained environment
PID_FILE="processor_66_percent.pid"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Color codes for better readability
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to log with timestamp
log() {
    echo -e "$(date +'%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Print banner
log "===================================================================================="
log "                        ADAPTIVE PROCESSOR TO 66% TARGET                            "
log "===================================================================================="
log "This script runs the adaptive processor to reach a 66% completion target"
log "Target percentage: $TARGET_PERCENTAGE%"
log "Max batch size: $MAX_BATCH_SIZE"
log "Log file: $LOG_FILE"
log "===================================================================================="

# Check if processor is already running
pgrep -f "$PROCESSOR_NAME.*--target $TARGET_PERCENTAGE" > /dev/null
if [ $? -eq 0 ]; then
    log "${YELLOW}Processor is already running with PID $(pgrep -f "$PROCESSOR_NAME.*--target $TARGET_PERCENTAGE")${NC}"
    log "${YELLOW}Exiting to avoid duplicate processes.${NC}"
    exit 1
fi

# Check if processors directory exists
if [ ! -d "processors" ]; then
    log "${RED}Error: 'processors' directory not found. Ensure you're running this from the project root.${NC}"
    exit 1
fi

# Check if adaptive processor exists
if [ ! -f "processors/adaptive_processor.py" ]; then
    log "${RED}Error: 'adaptive_processor.py' not found in the processors directory.${NC}"
    exit 1
fi

# Run the processor
log "${BLUE}Starting adaptive processor with target $TARGET_PERCENTAGE% and max batch size $MAX_BATCH_SIZE...${NC}"

# Make sure we're in the project root directory
cd "$(dirname "$0")" || exit 1

# Run the processor from the project root
python processors/adaptive_processor.py --target $TARGET_PERCENTAGE --max-batch $MAX_BATCH_SIZE > "$LOG_FILE" 2>&1 &

PROCESSOR_PID=$!
echo $PROCESSOR_PID > "$PID_FILE"
log "${GREEN}Processor started with PID $PROCESSOR_PID${NC}"
log "${GREEN}PID saved to $PID_FILE${NC}"

# Add signal handling
cleanup() {
    log "${YELLOW}Signal received. Cleaning up...${NC}"
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null; then
            log "${YELLOW}Stopping processor with PID $PID...${NC}"
            kill -15 "$PID"
            sleep 2
            if ps -p "$PID" > /dev/null; then
                log "${YELLOW}Process still running, sending SIGKILL...${NC}"
                kill -9 "$PID"
            fi
        fi
        rm "$PID_FILE"
        log "${GREEN}Cleanup complete.${NC}"
    fi
    exit 0
}

# Register signal handlers
trap cleanup SIGINT SIGTERM

log "${GREEN}Processor is running in the background. Use 'tail -f $LOG_FILE' to monitor progress.${NC}"
log "${GREEN}To check processing status, run 'python check_processor_progress.py --target $TARGET_PERCENTAGE'${NC}"
log "${GREEN}To stop the processor, run 'kill \$(cat $PID_FILE)' or press Ctrl+C${NC}"