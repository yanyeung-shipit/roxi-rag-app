#!/bin/bash

# Get Current Progress
# This script shows the current progress of the vector store rebuilding process

# Run the check_progress.py script
python check_progress.py

# Get estimated time remaining
remaining_chunks=$(python check_progress.py | grep "Remaining:" | sed 's/.*Remaining: \([0-9]*\).*/\1/')
processing_rate=$(grep -a "chunk" process_40_percent_continuous.log | wc -l)
elapsed_time=$(grep -a "Processing chunk" process_40_percent_continuous.log | wc -l)

# Calculate rate: chunks per minute
if [ "$elapsed_time" -gt 0 ]; then
    # Approximate rate: 1 chunk per 3 seconds (hardcoded delay) = 20 chunks per minute
    rate=20
    
    # Estimated minutes remaining
    if [ "$remaining_chunks" -gt 0 ] && [ "$rate" -gt 0 ]; then
        minutes=$(( remaining_chunks / rate ))
        echo ""
        echo "Estimation based on recent processing rate:"
        echo "----------------------------------------"
        echo "Estimated time remaining: approximately $minutes minutes"
        echo "Processing at about $rate chunks per minute"
    fi
fi

# Check if the processor is running
if pgrep -f "resilient_processor.py" > /dev/null; then
    echo ""
    echo "Processor status: RUNNING"
else
    echo ""
    echo "Processor status: NOT RUNNING"
    if [ -f "processor_monitor.log" ] && grep -q "Target reached" processor_monitor.log; then
        echo "Target has been reached!"
    else
        echo "The processor monitor should restart it shortly."
    fi
fi

echo ""
echo "For more detailed information:"
echo "tail -n 50 process_40_percent_continuous.log"