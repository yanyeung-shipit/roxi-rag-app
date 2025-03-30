#!/bin/bash
# check_and_restart_processor.sh
#
# This script checks the status of the adaptive processor and provides
# options to restart or start the processor if it's not running.
#
# Usage:
# ./check_and_restart_processor.sh

# Configuration
PID_FILE="processor_66_percent.pid"
CHECK_SCRIPT="./check_adaptive_processor.py"
MONITOR_PID_FILE="monitor_66percent.pid"
TARGET_PERCENTAGE=66.0

# Function to check if the processor is running
check_processor_running() {
    if [ ! -f "${PID_FILE}" ]; then
        echo "Processor is not running (PID file not found)"
        return 1
    fi
    
    pid=$(cat "${PID_FILE}")
    if ! ps -p "${pid}" > /dev/null 2>&1; then
        echo "Processor is not running, but PID file exists (stale PID: ${pid})"
        return 1
    fi
    
    echo "Processor is running with PID ${pid}"
    
    # Get processor uptime
    process_start=$(ps -o lstart= -p "${pid}")
    if [ -n "${process_start}" ]; then
        echo "Process started at: ${process_start}"
        uptime=$(ps -o etime= -p "${pid}")
        echo "Process uptime: ${uptime}"
    fi
    
    return 0
}

# Function to check if the monitor is running
check_monitor_running() {
    if [ ! -f "${MONITOR_PID_FILE}" ]; then
        echo "Monitor is not running (PID file not found)"
        return 1
    fi
    
    pid=$(cat "${MONITOR_PID_FILE}")
    if ! ps -p "${pid}" > /dev/null 2>&1; then
        echo "Monitor is not running, but PID file exists (stale PID: ${pid})"
        return 1
    fi
    
    echo "Monitor is running with PID ${pid}"
    
    # Get monitor uptime
    process_start=$(ps -o lstart= -p "${pid}")
    if [ -n "${process_start}" ]; then
        echo "Monitor started at: ${process_start}"
        uptime=$(ps -o etime= -p "${pid}")
        echo "Monitor uptime: ${uptime}"
    fi
    
    return 0
}

# Function to check processor progress
check_progress() {
    echo "Checking current progress..."
    python "${CHECK_SCRIPT}" --target "${TARGET_PERCENTAGE}"
}

# Function to start the processor
start_processor() {
    echo "Starting processor..."
    ./run_to_66_percent.sh
    sleep 2
    check_processor_running
}

# Function to restart the processor
restart_processor() {
    echo "Restarting processor..."
    
    # Stop the processor if it's running
    if [ -f "${PID_FILE}" ]; then
        pid=$(cat "${PID_FILE}")
        echo "Stopping processor with PID ${pid}..."
        kill "${pid}" 2>/dev/null
        sleep 2
        
        # Force kill if necessary
        if ps -p "${pid}" > /dev/null 2>&1; then
            echo "Processor still running. Force killing..."
            kill -9 "${pid}" 2>/dev/null
            sleep 1
        fi
        
        # Remove PID file
        rm "${PID_FILE}" 2>/dev/null
    fi
    
    # Start the processor
    start_processor
}

# Function to start the monitor
start_monitor() {
    echo "Starting monitor service..."
    nohup ./monitor_and_restart_processor.sh > logs/monitor_66percent.log 2>&1 &
    sleep 2
    check_monitor_running
}

# Function to stop the monitor
stop_monitor() {
    if [ ! -f "${MONITOR_PID_FILE}" ]; then
        echo "Monitor not running (PID file not found)"
        return
    fi
    
    pid=$(cat "${MONITOR_PID_FILE}")
    echo "Stopping monitor with PID ${pid}..."
    kill "${pid}" 2>/dev/null
    sleep 2
    
    # Force kill if necessary
    if ps -p "${pid}" > /dev/null 2>&1; then
        echo "Monitor still running. Force killing..."
        kill -9 "${pid}" 2>/dev/null
        sleep 1
    fi
    
    # Remove PID file
    rm "${MONITOR_PID_FILE}" 2>/dev/null
    echo "Monitor stopped"
}

# Function to check log file
check_processor_logs() {
    log_files=$(ls -t logs/processor_66_percent_*.log 2>/dev/null)
    
    if [ -z "${log_files}" ]; then
        echo "No processor log files found"
        return
    fi
    
    latest_log=$(echo "${log_files}" | head -n 1)
    echo "Most recent processor log: ${latest_log}"
    echo "Last 10 lines of log:"
    echo "---------------------------------------------"
    tail -n 10 "${latest_log}"
    echo "---------------------------------------------"
}

# Function to check monitor log
check_monitor_logs() {
    monitor_log="logs/monitor_66percent.log"
    
    if [ ! -f "${monitor_log}" ]; then
        echo "No monitor log file found"
        return
    fi
    
    echo "Last 10 lines of monitor log:"
    echo "---------------------------------------------"
    tail -n 10 "${monitor_log}"
    echo "---------------------------------------------"
}

# Function to display menu
show_menu() {
    echo ""
    echo "===== Processor Management Menu ====="
    echo "1. Check processor status and progress"
    echo "2. Start processor"
    echo "3. Restart processor"
    echo "4. Start monitor service"
    echo "5. Stop monitor service"
    echo "6. View processor logs"
    echo "7. View monitor logs"
    echo "8. Exit"
    echo "====================================="
    echo -n "Enter your choice [1-8]: "
}

# Main function
main() {
    echo "===== Processor Status ====="
    check_processor_running
    echo ""
    echo "===== Monitor Status ====="
    check_monitor_running
    echo ""
    check_progress
    
    # Interactive menu
    while true; do
        show_menu
        read choice
        
        case $choice in
            1)
                echo ""
                echo "===== Processor Status ====="
                check_processor_running
                echo ""
                echo "===== Monitor Status ====="
                check_monitor_running
                echo ""
                check_progress
                ;;
            2)
                echo ""
                start_processor
                ;;
            3)
                echo ""
                restart_processor
                ;;
            4)
                echo ""
                start_monitor
                ;;
            5)
                echo ""
                stop_monitor
                ;;
            6)
                echo ""
                check_processor_logs
                ;;
            7)
                echo ""
                check_monitor_logs
                ;;
            8)
                echo "Exiting..."
                exit 0
                ;;
            *)
                echo "Invalid option. Please try again."
                ;;
        esac
    done
}

# Run the main function
main