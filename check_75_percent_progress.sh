#!/bin/bash

# Check if processes are running via ps
processor_pid=$(pgrep -f "process_to_50_percent.py")

if [ -n "$processor_pid" ]; then
    echo "75% processor is running with PID: $processor_pid"
else
    echo "75% processor is not running (checking log files for status)"
fi

echo -e "\nProgress information:"
echo "-------------------"

# Find the standard log file
log_file="process_75_percent.log"

if [ -f "$log_file" ]; then
    # Extract progress information
    progress=$(grep "Progress:" "$log_file" | tail -5)
    estimated=$(grep "Est. time:" "$log_file" | tail -1)
    
    if [ -n "$progress" ]; then
        echo -e "$progress"
        echo -e "$estimated"
        
        # Calculate percentage to target
        current_pct=$(grep "complete" "$log_file" | tail -1 | grep -o '[0-9]*\.[0-9]*')
        if [ -n "$current_pct" ]; then
            target_pct=75.0
            pct_to_go=$(echo "$target_pct - $current_pct" | bc)
            echo -e "\nProgress toward 75% target: $current_pct% (${pct_to_go}% remaining)"
        fi
    else
        echo "No progress information found in log"
    fi
    
    # Show the most recent chunks processed
    echo -e "\nRecent chunks processed:"
    grep "Successfully processed chunk ID" "$log_file" | tail -5
    
    # Show processing rate
    first_timestamp=$(head -50 "$log_file" | grep "Successfully processed chunk" | head -1 | cut -d' ' -f1-2)
    last_timestamp=$(grep "Successfully processed chunk" "$log_file" | tail -1 | cut -d' ' -f1-2)
    chunks_count=$(grep "Successfully processed chunk" "$log_file" | wc -l)
    
    if [ -n "$first_timestamp" ] && [ -n "$last_timestamp" ] && [ "$chunks_count" -gt 1 ]; then
        echo -e "\nProcessing statistics:"
        echo "First chunk: $first_timestamp"
        echo "Latest chunk: $last_timestamp"
        echo "Chunks processed: $chunks_count"
        
        # Try to calculate rate if time format is as expected
        if [[ "$first_timestamp" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}\ [0-9]{2}:[0-9]{2} ]] && [[ "$last_timestamp" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}\ [0-9]{2}:[0-9]{2} ]]; then
            first_ts=$(date -d "${first_timestamp}" +%s 2>/dev/null)
            last_ts=$(date -d "${last_timestamp}" +%s 2>/dev/null)
            
            if [ -n "$first_ts" ] && [ -n "$last_ts" ]; then
                elapsed=$((last_ts - first_ts))
                if [ "$elapsed" -gt 0 ]; then
                    rate=$(echo "scale=2; $chunks_count / $elapsed" | bc)
                    echo "Processing rate: $rate chunks/second"
                    
                    # Estimate remaining time based on progress data
                    remaining_chunks=$(grep "Remaining:" "$log_file" | tail -1 | grep -o '[0-9]*')
                    if [ -n "$remaining_chunks" ]; then
                        est_seconds=$(echo "scale=0; $remaining_chunks / $rate" | bc)
                        est_minutes=$(echo "scale=0; $est_seconds / 60" | bc)
                        est_hours=$(echo "scale=1; $est_minutes / 60" | bc)
                        echo "Estimated time remaining: ${est_hours}h (${est_minutes}m)"
                    fi
                fi
            fi
        fi
    fi
else
    echo "Main log file not found"
fi

echo -e "\nTo restart processing, run: ./longer_run_until_75_percent.sh"