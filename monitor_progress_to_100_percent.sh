#!/bin/bash
# monitor_progress_to_100_percent.sh
#
# This script monitors the progress of the vector store rebuild toward 100% completion.
# It doesn't restart anything, it just shows progress information.
#
# Usage:
# ./monitor_progress_to_100_percent.sh [interval]

# Default check interval (seconds)
INTERVAL=${1:-60}
TARGET=100.0

# Colors for better output
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}Starting progress monitor for ${TARGET}% completion target${NC}"
echo -e "${BLUE}Checking every ${INTERVAL} seconds${NC}"
echo

while true; do
    # Get progress information
    progress_json=$(python check_progress.py --json)
    
    # Extract key metrics
    percentage=$(echo "$progress_json" | grep -o '"percentage": [0-9.]*' | cut -d' ' -f2)
    processed=$(echo "$progress_json" | grep -o '"processed_chunks": [0-9]*' | cut -d' ' -f2)
    total=$(echo "$progress_json" | grep -o '"total_chunks": [0-9]*' | cut -d' ' -f2)
    
    # Calculate remaining chunks to 100%
    remaining=$((total - processed))
    
    # Calculate percentage to target
    pct_to_target=$(echo "scale=1; ($percentage / $TARGET) * 100" | bc)
    
    # Display progress bar (50 characters wide)
    bar_width=50
    completed_chars=$(echo "scale=0; ($percentage / 100) * $bar_width" | bc)
    remaining_chars=$((bar_width - completed_chars))
    
    # Build progress bar
    progress_bar="["
    for ((i=0; i<completed_chars; i++)); do
        progress_bar+="#"
    done
    for ((i=0; i<remaining_chars; i++)); do
        progress_bar+="."
    done
    progress_bar+="]"
    
    # Get timestamps
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    
    # Check if any processor is running
    processor_running=false
    if pgrep -f "python.*process_to_100_percent.py" > /dev/null || pgrep -f "python.*enhanced_process_to_100_percent.py" > /dev/null; then
        processor_running=true
    fi
    
    # Display information
    echo -e "${BLUE}${timestamp}${NC}"
    echo -e "${GREEN}Progress: ${percentage}% ${progress_bar} (Target: ${TARGET}%)${NC}"
    echo -e "${YELLOW}Chunks: ${processed}/${total} processed, ${remaining} remaining${NC}"
    
    if [ "$processor_running" = true ]; then
        echo -e "${GREEN}Processor is RUNNING${NC}"
    else
        echo -e "${RED}Processor is NOT RUNNING${NC}"
    fi
    
    # Calculate estimated time based on last hour's progress
    # (This is a simplified estimate and won't be shown in this version)
    
    echo -e "${BLUE}Progress toward target: ${pct_to_target}% of ${TARGET}%${NC}"
    echo
    
    # Wait before next check
    sleep $INTERVAL
done