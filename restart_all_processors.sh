#!/bin/bash

# Restart All Processors
# This script forcefully kills all existing processor instances and restarts them

echo "Killing all existing processor instances..."
pkill -f "resilient_processor.py" || true
pkill -f "run_continuous_until_40_percent.sh" || true
pkill -f "run_continuous_monitor.sh" || true

echo "Waiting for processes to terminate..."
sleep 2

echo "Starting the processor in the background..."
nohup ./run_continuous_until_40_percent.sh > process_40_percent_continuous.log 2>&1 &
processor_pid=$!
echo "Processor started with PID: $processor_pid"

echo "Starting the monitor in the background..."
nohup ./run_continuous_monitor.sh > continuous_monitor.log 2>&1 &
monitor_pid=$!
echo "Monitor started with PID: $monitor_pid"

echo "Done. Both processes are now running."
echo "To check progress at any time, run: ./get_current_progress.sh"