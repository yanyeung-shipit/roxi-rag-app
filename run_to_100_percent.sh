#!/bin/bash
# run_to_100_percent.sh
#
# This script runs the enhanced processor to 100% completion
# It's a simple wrapper for enhanced_process_to_100_percent.py
#
# Usage:
# ./run_to_100_percent.sh [batch_size]

# Default batch size
BATCH_SIZE=${1:-3}

# Run with specified batch size
echo "Starting enhanced processor to 100% with batch size $BATCH_SIZE"
python enhanced_process_to_100_percent.py --batch-size $BATCH_SIZE