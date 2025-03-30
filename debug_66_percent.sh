#!/bin/bash
# debug_66_percent.sh
#
# This script runs the adaptive processor in the foreground for debugging
# purposes until it processes one chunk or fails

# Configuration
LOG_DIR="logs"
PROCESSOR_SCRIPT="processors/adaptive_processor.py"
TARGET_PERCENTAGE=66.0

# Create logs directory if it doesn't exist
mkdir -p "${LOG_DIR}"

echo "Starting adaptive processor in debug mode..."
echo "Target: ${TARGET_PERCENTAGE}%"
echo "Running script: ${PROCESSOR_SCRIPT}"
echo "------------------------------------------"

# Run the processor in the foreground with increased verbosity
export PYTHONUNBUFFERED=1
python "${PROCESSOR_SCRIPT}" --target "${TARGET_PERCENTAGE}" 