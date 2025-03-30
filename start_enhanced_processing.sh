#!/bin/bash
# start_enhanced_processing.sh
#
# This script starts the enhanced monitor, which will continuously restart
# the processor as needed until the target percentage is reached.
#
# Usage:
# ./start_enhanced_processing.sh

# Clean up any leftover PID files
rm -f processor_66_percent.pid enhanced_monitor.pid

# Create logs directory
mkdir -p logs

echo "=== Starting Enhanced Processing System ==="
echo "Starting enhanced monitor..."

# Start the enhanced monitor in the background
nohup ./enhanced_monitor.sh > logs/enhanced_monitor.log 2>&1 &

# Check if monitor started
sleep 2
if [ -f "enhanced_monitor.pid" ]; then
    pid=$(cat "enhanced_monitor.pid")
    echo "Enhanced monitor started with PID ${pid}"
    echo "Processing has begun, initially aiming for 66% completion."
    echo "Current progress:"
    python check_adaptive_processor.py
    echo ""
    echo "The system will now continuously process chunks until 66% is reached."
    echo "You can check progress at any time with: python check_adaptive_processor.py"
    echo "To view monitor logs: tail -f logs/enhanced_monitor.log"
else
    echo "Failed to start enhanced monitor. Check logs for details."
fi