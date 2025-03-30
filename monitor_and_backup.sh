#!/bin/bash

# Combined monitor and backup script
# This script starts both monitoring and backup processes

echo "Starting vector store protection system..."

# Function to clean up on exit
cleanup() {
    echo "Shutting down protection system..."
    
    # Kill backup scheduler if running
    if [ -f "backup_scheduler.pid" ]; then
        BACKUP_PID=$(cat backup_scheduler.pid)
        if ps -p $BACKUP_PID > /dev/null; then
            echo "Stopping backup scheduler..."
            kill $BACKUP_PID
        fi
        rm backup_scheduler.pid
    fi
    
    # Kill monitor process if running
    if [ -f "monitor_process.pid" ]; then
        MONITOR_PID=$(cat monitor_process.pid)
        if ps -p $MONITOR_PID > /dev/null; then
            echo "Stopping monitor process..."
            kill $MONITOR_PID
        fi
        rm monitor_process.pid
    fi
    
    echo "Protection system stopped"
    exit 0
}

# Set trap for cleanup on exit
trap cleanup SIGINT SIGTERM

# Start backup scheduler in background
echo "Starting backup scheduler..."
./schedule_backups.sh > backup_scheduler.log 2>&1 &

# Start monitor process in background
echo "Starting vector store monitor..."
python monitor_vector_store.py > monitor_vector_store.log 2>&1 &
echo $! > monitor_process.pid

echo "Protection system started"
echo "- Backups will run every 4 hours"
echo "- Vector store is being monitored for data loss"
echo "- Press Ctrl+C to stop all protection services"

# Keep script running and show status periodically
while true; do
    sleep 600  # 10 minutes
    
    # Show status
    echo "=== Protection System Status ==="
    echo "$(date)"
    
    # Check if backup scheduler is running
    if [ -f "backup_scheduler.pid" ]; then
        BACKUP_PID=$(cat backup_scheduler.pid)
        if ps -p $BACKUP_PID > /dev/null; then
            echo "✓ Backup scheduler: Running (PID $BACKUP_PID)"
        else
            echo "✗ Backup scheduler: Not running (stale PID file)"
        fi
    else
        echo "✗ Backup scheduler: Not running (no PID file)"
    fi
    
    # Check if monitor is running
    if [ -f "monitor_process.pid" ]; then
        MONITOR_PID=$(cat monitor_process.pid)
        if ps -p $MONITOR_PID > /dev/null; then
            echo "✓ Vector store monitor: Running (PID $MONITOR_PID)"
        else
            echo "✗ Vector store monitor: Not running (stale PID file)"
        fi
    else
        echo "✗ Vector store monitor: Not running (no PID file)"
    fi
    
    # Show latest backup time
    if [ -d "./backups/daily" ]; then
        LATEST_BACKUP=$(ls -lt ./backups/daily | grep -v ^total | head -n 1 | awk '{print $6, $7, $8}')
        if [ ! -z "$LATEST_BACKUP" ]; then
            echo "Latest daily backup: $LATEST_BACKUP"
        else
            echo "No daily backups found"
        fi
    else
        echo "No backup directory found"
    fi
    
    echo "==============================="
done