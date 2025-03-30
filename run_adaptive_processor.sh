#!/bin/bash

# This script runs the adaptive processor that automatically adjusts to available system resources
# It will use larger batch sizes when resources are available and fall back to single-chunk processing
# when resources are constrained

# Ensure log directories exist
mkdir -p logs/batch_processing logs/checkpoints

# Log file with timestamp
TIMESTAMP=$(date +%Y%m%d%H%M%S)
LOG_FILE="logs/adaptive_processor_${TIMESTAMP}.log"

# Default settings
TARGET_PERCENTAGE=66.0
MAX_BATCH_SIZE=10

# Banner
echo ""
echo "================================================================================"
echo "                      ROXI ADAPTIVE DOCUMENT PROCESSOR                          "
echo "================================================================================"
echo ""
echo "This processor automatically adapts to available system resources:"
echo "- Uses batch processing when resources are plentiful"
echo "- Falls back to single-chunk processing when resources are constrained"
echo "- Dynamically adjusts batch size based on system load"
echo "- Includes robust error handling and checkpointing"
echo ""
echo "Target completion: ${TARGET_PERCENTAGE}%"
echo "Maximum batch size: ${MAX_BATCH_SIZE}"
echo "Log file: ${LOG_FILE}"
echo ""
echo "Starting processor... Press Ctrl+C to stop at any time."
echo "Progress is automatically saved to checkpoints."
echo ""

# Run the adaptive processor
python3 processors/adaptive_processor.py --target $TARGET_PERCENTAGE --max-batch $MAX_BATCH_SIZE | tee "$LOG_FILE"

# Print completion message
echo ""
echo "Processing completed or interrupted."
echo "Progress has been saved to checkpoints and can be resumed later."
echo "To check current progress, run: python3 check_processor_progress.py"