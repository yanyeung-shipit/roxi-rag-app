#!/bin/bash

# This script runs the batch processor to reach 40% completion
# It uses a batch size of 10 for better efficiency

# Ensure log directories exist
mkdir -p logs/batch_processing logs/checkpoints

# Log file with timestamp
TIMESTAMP=$(date +%Y%m%d%H%M%S)
LOG_FILE="logs/batch_to_40_percent_${TIMESTAMP}.log"

echo "Starting batch processor to reach 40% completion"
echo "Log file: $LOG_FILE"
echo "This process may take some time but is more efficient than the single processor"
echo "Progress will be displayed below and logged to the file"

# Run the batch processor targeting 40%
python batch_rebuild_to_target.py --target 40.0 --batch-size 10 | tee "$LOG_FILE"

# Print completion message
echo ""
echo "Batch processing completed. Check $LOG_FILE for details."
echo "Run 'python check_processor_progress.py' to see current progress."