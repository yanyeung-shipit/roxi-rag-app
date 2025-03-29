#!/bin/bash
# Run process_to_target.sh in the background with logging
# Usage: ./background_process_to_target.sh [target_percentage] [start_chunk_id] [max_chunks]

# Set defaults
TARGET_PERCENTAGE=${1:-65.0}
START_CHUNK_ID=${2:-6725}  # Use next chunk after the 30 we're processing
MAX_CHUNKS=${3:-200}        # Safety limit to avoid infinite loops

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_DIR="logs/batch_processing"
RUN_LOG="${LOG_DIR}/background_target_${TARGET_PERCENTAGE}_${TIMESTAMP}.log"
PID_FILE="${LOG_DIR}/target_processing.pid"

mkdir -p "$LOG_DIR"

# Check if process is already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null; then
        echo "A target processing job is already running with PID $PID"
        echo "Check $LOG_DIR for log files or use check_target_progress.sh to monitor"
        exit 1
    else
        echo "Stale PID file found. Previous job may have crashed."
        rm -f "$PID_FILE"
    fi
fi

# Start the processing in the background
nohup ./process_to_target.sh "$TARGET_PERCENTAGE" "$START_CHUNK_ID" "$MAX_CHUNKS" > "$RUN_LOG" 2>&1 &
PROCESS_PID=$!

# Save the PID
echo $PROCESS_PID > "$PID_FILE"

echo "Started target processing in the background."
echo "Target percentage: $TARGET_PERCENTAGE%"
echo "Starting chunk ID: $START_CHUNK_ID"
echo "Maximum chunks: $MAX_CHUNKS"
echo "Process ID: $PROCESS_PID"
echo "Log file: $RUN_LOG"
echo ""
echo "To monitor progress, use:"
echo "  tail -f $RUN_LOG"
echo "  or"
echo "  ./check_target_progress.sh"