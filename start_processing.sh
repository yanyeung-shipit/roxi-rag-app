#!/bin/bash
# start_processing.sh
#
# This script starts both the adaptive processor and the monitor service
# to ensure the vector store reaches 66% completion.
#
# Usage:
# ./start_processing.sh

# Configuration
PID_FILE="processor_66_percent.pid"
MONITOR_PID_FILE="monitor_66percent.pid"
LOG_DIR="logs"
MONITOR_LOG="${LOG_DIR}/monitor_66percent.log"

# Create logs directory if it doesn't exist
mkdir -p "${LOG_DIR}"

echo "===== Starting Processing System ====="

# First, check and clean up any stale PID files
if [ -f "${PID_FILE}" ]; then
    pid=$(cat "${PID_FILE}")
    if ! ps -p "${pid}" > /dev/null 2>&1; then
        echo "Found stale processor PID file. Cleaning up..."
        rm "${PID_FILE}"
    else
        echo "Processor already running with PID ${pid}"
    fi
fi

if [ -f "${MONITOR_PID_FILE}" ]; then
    pid=$(cat "${MONITOR_PID_FILE}")
    if ! ps -p "${pid}" > /dev/null 2>&1; then
        echo "Found stale monitor PID file. Cleaning up..."
        rm "${MONITOR_PID_FILE}"
    else
        echo "Monitor already running with PID ${pid}"
    fi
fi

# Start the monitor service
if [ ! -f "${MONITOR_PID_FILE}" ]; then
    echo "Starting monitor service..."
    nohup ./monitor_and_restart_processor.sh > "${MONITOR_LOG}" 2>&1 &
    sleep 2
    
    # Check if monitor started successfully
    if [ -f "${MONITOR_PID_FILE}" ]; then
        pid=$(cat "${MONITOR_PID_FILE}")
        echo "Monitor service started with PID ${pid}"
    else
        echo "Failed to start monitor service. Check logs."
    fi
else
    echo "Monitor service already running"
fi

# Start the processor if it's not already running
if [ ! -f "${PID_FILE}" ]; then
    echo "Starting processor..."
    ./run_to_66_percent.sh
    sleep 2
    
    # Check if processor started successfully
    if [ -f "${PID_FILE}" ]; then
        pid=$(cat "${PID_FILE}")
        echo "Processor started with PID ${pid}"
    else
        echo "Failed to start processor. Check logs."
    fi
else
    echo "Processor already running"
fi

echo "===== Setup Complete ====="
echo "Current progress:"
python check_adaptive_processor.py --target 66.0
echo ""
echo "To check status: ./check_adaptive_processor.py"
echo "To view monitor logs: tail -f ${MONITOR_LOG}"