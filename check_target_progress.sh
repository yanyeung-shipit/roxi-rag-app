#!/bin/bash
# Check the progress of a running target percentage process
# Usage: ./check_target_progress.sh

LOG_DIR="logs/batch_processing"
PID_FILE="${LOG_DIR}/target_processing.pid"

# Check if process is running
if [ ! -f "$PID_FILE" ]; then
    echo "No target processing job is currently running."
    echo "Start one with ./background_process_to_target.sh [target_percentage] [start_chunk_id] [max_chunks]"
    exit 1
fi

PID=$(cat "$PID_FILE")
if ! ps -p "$PID" > /dev/null; then
    echo "Process with PID $PID is no longer running."
    echo "It may have completed or crashed. Check log files in $LOG_DIR"
    
    # Optionally remove stale PID file
    read -p "Remove stale PID file? [y/N] " response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        rm -f "$PID_FILE"
        echo "PID file removed."
    fi
    
    exit 1
fi

# Find the most recent log file
LATEST_LOG=$(ls -t ${LOG_DIR}/background_target_*.log 2>/dev/null | head -n 1)

if [ -z "$LATEST_LOG" ]; then
    echo "Process is running with PID $PID, but no log file found."
    echo "Current vector store progress:"
    python check_progress.py
    exit 0
fi

# Display status information
echo "Target processing job is running with PID $PID"
echo "Log file: $LATEST_LOG"
echo ""

# Extract target percentage from log
TARGET_PCT=$(grep "Target:" "$LATEST_LOG" | awk '{print $2}' | tr -d '%')
START_TIME=$(grep "Start time:" "$LATEST_LOG" | cut -d ':' -f 2- | xargs)
ELAPSED_SEC=$(($(date +%s) - $(date -d "$START_TIME" +%s)))
ELAPSED_MIN=$((ELAPSED_SEC / 60))
ELAPSED_HR=$((ELAPSED_MIN / 60))
ELAPSED_MIN=$((ELAPSED_MIN % 60))

echo "Target percentage: ${TARGET_PCT}%"
echo "Started at: $START_TIME"
echo "Running for: ${ELAPSED_HR}h ${ELAPSED_MIN}m"
echo ""

# Get current progress
CURRENT_PCT=$(python -c '
import json
import subprocess

result = subprocess.run(["python", "check_progress.py", "--json"], 
                        capture_output=True, text=True)
try:
    data = json.loads(result.stdout.strip())
    print(data["progress_pct"])
except (json.JSONDecodeError, KeyError) as e:
    print("0.0")  # Default if we cannot parse
')

echo "Current progress: ${CURRENT_PCT}%"
echo "Remaining to target: $(echo "$TARGET_PCT - $CURRENT_PCT" | bc)%"

# Get processed chunks count
CHUNKS_PROCESSED=$(grep -c "Successfully processed chunk" "$LATEST_LOG")
CHUNKS_FAILED=$(grep -c "Failed to process chunk" "$LATEST_LOG")
TOTAL_ATTEMPTS=$((CHUNKS_PROCESSED + CHUNKS_FAILED))

echo ""
echo "Chunks processed: $CHUNKS_PROCESSED successful, $CHUNKS_FAILED failed, $TOTAL_ATTEMPTS total"
echo "Processing rate: $(echo "scale=2; $TOTAL_ATTEMPTS / ($ELAPSED_SEC / 60)" | bc) chunks/minute"

# Estimate time to completion
if (( $(echo "$CURRENT_PCT < $TARGET_PCT" | bc -l) )); then
    # Calculate chunks needed to reach target
    TOTAL_CHUNKS=$(python -c "
import json
import subprocess

result = subprocess.run(['python', 'check_progress.py', '--json'], 
                       capture_output=True, text=True)
data = json.loads(result.stdout.strip())
total = data['db_count']
print(total)
")
    
    CURRENT_CHUNKS=$(python -c "
import json
import subprocess

result = subprocess.run(['python', 'check_progress.py', '--json'], 
                       capture_output=True, text=True)
data = json.loads(result.stdout.strip())
current = data['vector_count']
print(current)
")
    
    TARGET_CHUNKS=$(echo "scale=0; $TOTAL_CHUNKS * $TARGET_PCT / 100" | bc)
    CHUNKS_REMAINING=$(echo "$TARGET_CHUNKS - $CURRENT_CHUNKS" | bc)
    
    # Calculate time estimate
    if [ $TOTAL_ATTEMPTS -gt 0 ] && [ $ELAPSED_SEC -gt 0 ]; then
        RATE=$(echo "scale=4; $CHUNKS_PROCESSED / $ELAPSED_SEC" | bc)
        if (( $(echo "$RATE > 0" | bc -l) )); then
            EST_SECONDS=$(echo "scale=0; $CHUNKS_REMAINING / $RATE" | bc)
            EST_HOURS=$(echo "$EST_SECONDS / 3600" | bc)
            EST_MINUTES=$(echo "($EST_SECONDS % 3600) / 60" | bc)
            
            echo ""
            echo "Estimated time to target: ${EST_HOURS}h ${EST_MINUTES}m"
            echo "Estimated completion time: $(date -d "+$EST_SECONDS seconds" "+%Y-%m-%d %H:%M:%S")"
        else
            echo ""
            echo "Processing rate too low to estimate completion time."
        fi
    else
        echo ""
        echo "Not enough data to estimate completion time yet."
    fi
else
    echo ""
    echo "Target percentage has been reached!"
fi

# Show recent activity
echo ""
echo "Recent activity (last 10 chunks):"
echo "--------------------------------"
tail -n 50 "$LATEST_LOG" | grep -E "Processing chunk|Successfully processed|Failed to process" | tail -n 10

echo ""
echo "To see full log: tail -f $LATEST_LOG"