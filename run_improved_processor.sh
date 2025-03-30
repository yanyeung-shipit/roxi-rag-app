#!/bin/bash

# Run Improved Processor Script
# This script runs the improved continuous processor with the optimal settings for Replit

echo "Starting improved continuous processor..."
echo "Target: 40% completion"
echo "Batch size: 1 chunk"
echo "Delay: 3 seconds between chunks"

# Kill any existing processor instances
pkill -f "improved_continuous_processor.py" || true

# Wait for processes to terminate
sleep 2

# Start the processor
python improved_continuous_processor.py --batch-size 1 --delay 3 --target 40 > improved_processor_output.log 2>&1 

echo "Processor has completed or was interrupted."
echo "Check improved_processor_output.log for details."