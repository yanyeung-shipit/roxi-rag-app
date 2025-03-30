#!/bin/bash
# Script to run the batch rebuild processor until 66% completion

# Set up log directory if it doesn't exist
mkdir -p logs/batch_processing
mkdir -p logs/checkpoints

# Create log filename with timestamp
LOG_FILE="logs/batch_processing/batch_rebuild_$(date +%Y%m%d_%H%M%S).log"

echo "Starting batch rebuild to reach 66% completion..."
echo "Log file: $LOG_FILE"

# Run the processor with a batch size of 5 (small enough to not overload memory)
python process_to_sixty_six_percent.py --batch-size 5 | tee "$LOG_FILE"

# Check if the process completed successfully
if [ $? -eq 0 ]; then
    echo "Batch rebuild completed successfully!"
    echo "Check the log file for details: $LOG_FILE"
else
    echo "Error: Batch rebuild failed!"
    echo "Check the log file for details: $LOG_FILE"
fi