#!/bin/bash
# start_enhanced_processing_to_100_percent.sh
#
# This script starts the enhanced processor to 100% in the background,
# and sets up monitoring to ensure it runs until completion.
#
# Usage:
# ./start_enhanced_processing_to_100_percent.sh [batch_size]

# Default batch size
BATCH_SIZE=${1:-3}

# Start the processor in the background with monitoring
echo "Starting enhanced processor to 100% with batch size $BATCH_SIZE"
nohup ./monitor_and_restart_processor_to_100_percent.sh $BATCH_SIZE 60 > processing_to_100percent.log 2>&1 &

# Sleep briefly to let the processor start
sleep 3

# Check if it started
if pgrep -f "monitor_and_restart_processor_to_100_percent.sh" > /dev/null; then
    echo "Processor monitor started successfully!"
    echo "PID: $(pgrep -f "monitor_and_restart_processor_to_100_percent.sh")"
    echo "Progress can be monitored with: tail -f processing_to_100percent.log"
    echo "Or use: ./monitor_progress_to_100_percent.sh 10"
    echo "To stop the processor: kill $(pgrep -f "monitor_and_restart_processor_to_100_percent.sh")"
else
    echo "Failed to start processor monitor."
fi