#!/bin/bash

# Schedule Vector Store Backups
# This script sets up a scheduled backup process

echo "Starting backup scheduler..."

# Choose between cron mode or continuous loop mode
MODE="loop"  # Change to "cron" to use cron instead

if [ "$MODE" = "cron" ]; then
    # Set up cron job (this requires cron to be installed and running)
    (crontab -l 2>/dev/null || echo "") | grep -v "backup_vector_store.py" > temp_cron
    echo "0 */4 * * * cd $(pwd) && python backup_vector_store.py >> backup_vector_store.log 2>&1" >> temp_cron
    crontab temp_cron
    rm temp_cron
    
    echo "Cron job scheduled to run backups every 4 hours"
    echo "View logs at: backup_vector_store.log"
    
else
    # Run in a continuous loop instead
    echo "Running backup scheduler in continuous loop mode"
    echo "Press Ctrl+C to stop"
    
    # Write PID to file
    echo $$ > backup_scheduler.pid
    
    # Set backup interval (in seconds)
    BACKUP_INTERVAL=14400  # 4 hours
    
    while true; do
        echo "$(date) - Running scheduled backup..."
        python backup_vector_store.py
        
        echo "Next backup scheduled in $((BACKUP_INTERVAL/60)) minutes"
        echo "Sleeping until next backup..."
        
        # Sleep until next backup
        sleep $BACKUP_INTERVAL &
        wait $!
    done
fi