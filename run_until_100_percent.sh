#!/bin/bash
# run_until_100_percent.sh
#
# This script runs and monitors the enhanced processor until 100% completion.
# It will keep restarting the processor if it fails, and show progress.
#
# Usage:
# ./run_until_100_percent.sh [batch_size]

# Default batch size
BATCH_SIZE=${1:-3}

# Start the monitor and restart script
echo "Starting enhanced processor to 100% with continuous monitoring..."
echo "Batch size: $BATCH_SIZE"
echo "Press Ctrl+C to exit (the processor will continue in the background)"
echo

# Start the monitor_and_restart script
./monitor_and_restart_processor_to_100_percent.sh $BATCH_SIZE 60