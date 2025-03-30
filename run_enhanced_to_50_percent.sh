#!/bin/bash
# Run Enhanced Process to 50%
#
# This script runs the enhanced_process_to_50_percent.py script with
# monitoring support via enhanced_monitor_and_restart.sh to ensure
# resilience against PostgreSQL SSL connection errors.

echo "Starting enhanced processing to 50% with monitoring..."

# Start the monitor in the background
./enhanced_monitor_and_restart.sh enhanced_process_to_50_percent.py --batch-size 5 &
MONITOR_PID=$!

echo "Monitor started with PID: $MONITOR_PID"
echo "Processing will continue until 50% completion."
echo "You can press Ctrl+C to stop the monitor."

# Tips for the user
cat << EOF

IMPORTANT TIPS:
--------------
1. View progress in real-time:
   > python check_processor_progress.py

2. Check logs:
   > tail -f enhanced_50percent.log
   > tail -f monitor_restart.log

3. To start in deep sleep mode (reduced resources):
   > python enhanced_process_to_50_percent.py --deep-sleep

EOF

# Wait for the monitor to complete
wait $MONITOR_PID

echo "Processing completed or monitor terminated."