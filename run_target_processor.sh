#!/bin/bash
# Run the target-based chunk processor with proper parameters
# This script runs the process_until_target.py script with proper parameters

# Default parameters
START_CHUNK=${1:-6727}
MAX_CHUNKS=${2:-10}
TARGET_PERCENTAGE=${3:-50.0}
CHUNK_TIMEOUT=${4:-90}

# Print banner
echo "======================================================="
echo "TARGET-BASED CHUNK PROCESSOR"
echo "======================================================="
echo "Start Chunk: $START_CHUNK"
echo "Max Chunks: $MAX_CHUNKS"
echo "Target: $TARGET_PERCENTAGE%"
echo "Timeout: $CHUNK_TIMEOUT seconds"
echo "Start time: $(date)"
echo "======================================================="

# Ensure log directory exists
mkdir -p logs/sequential_processing

# Run the processor with detailed output
python process_until_target.py \
    --start-chunk=$START_CHUNK \
    --max-chunks=$MAX_CHUNKS \
    --target-percentage=$TARGET_PERCENTAGE \
    --chunk-timeout=$CHUNK_TIMEOUT

# Print completion banner
echo "======================================================="
echo "PROCESSING COMPLETE"
echo "End time: $(date)"
echo "======================================================="