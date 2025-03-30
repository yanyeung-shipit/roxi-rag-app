#!/bin/bash
# Script to run the batch rebuild processor in the background
# Uses nohup to ensure it continues running even if the terminal session is closed

# Set up log directory if it doesn't exist
mkdir -p logs/batch_processing
mkdir -p logs/checkpoints

# Create log filename with timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="logs/batch_processing/background_rebuild_${TIMESTAMP}.log"
PID_FILE="logs/batch_processing/background_rebuild.pid"

echo "Starting background batch rebuild to reach 66% completion..."
echo "Log file: $LOG_FILE"

# Check if there's already a process running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p $OLD_PID > /dev/null; then
        echo "Warning: A rebuild process is already running with PID $OLD_PID"
        echo "If you want to start a new one, kill the existing process first with: kill $OLD_PID"
        exit 1
    else
        echo "Found stale PID file. Previous process is not running. Continuing..."
        rm "$PID_FILE"
    fi
fi

# Run the processor with a batch size of 5 (small enough to not overload memory)
# Use nohup to keep it running in the background
nohup python process_to_sixty_six_percent.py --batch-size 5 > "$LOG_FILE" 2>&1 &

# Store the PID
PID=$!
echo $PID > "$PID_FILE"
echo "Process started with PID $PID"
echo "You can monitor progress with: tail -f $LOG_FILE"
echo "To stop the process, run: kill $PID"

# Create a script to check the status
STATUS_SCRIPT="logs/batch_processing/check_rebuild_status.sh"

cat > "$STATUS_SCRIPT" << EOF
#!/bin/bash
# Script to check the status of the background rebuild process

PID_FILE="logs/batch_processing/background_rebuild.pid"
LOG_FILE="$LOG_FILE"

if [ -f "\$PID_FILE" ]; then
    PID=\$(cat "\$PID_FILE")
    if ps -p \$PID > /dev/null; then
        echo "Rebuild process is running with PID \$PID"
        echo "Recent log entries:"
        tail -n 10 "\$LOG_FILE"
        
        # Check progress
        echo -e "\nCurrent progress:"
        python check_progress.py
    else
        echo "No rebuild process is running. The PID file exists but process \$PID is not active."
        echo "Final log entries:"
        tail -n 20 "\$LOG_FILE"
        
        # Check progress
        echo -e "\nFinal progress:"
        python check_progress.py
    fi
else
    echo "No rebuild process is currently tracked."
    
    # Check progress
    echo -e "\nCurrent progress:"
    python check_progress.py
fi
EOF

chmod +x "$STATUS_SCRIPT"
echo -e "\nCreated status check script: $STATUS_SCRIPT"
echo "Run this script to check the status of the background process."