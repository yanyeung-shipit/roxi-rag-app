#!/bin/bash

# Check progress toward 50% completion
# This script checks the current progress and estimates time to reach 50%

# Set terminal colors
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color
BOLD='\033[1m'

echo -e "${BOLD}Checking progress toward 50% target${NC}"
echo "======================================"

# Get current progress
PROGRESS_DATA=$(python check_progress.py --json)

# Extract values using grep and cut (more reliable than parsing JSON with bash)
PROCESSED=$(echo "$PROGRESS_DATA" | grep -o '"processed_chunks": [0-9]*' | cut -d' ' -f2)
TOTAL=$(echo "$PROGRESS_DATA" | grep -o '"total_chunks": [0-9]*' | cut -d' ' -f2)
PERCENT=$(echo "$PROGRESS_DATA" | grep -o '"percentage": [0-9]*\.[0-9]*' | cut -d' ' -f2)
TARGET=$(echo "$PROGRESS_DATA" | grep -o '"target_percentage": [0-9]*\.[0-9]*' | cut -d' ' -f2)

# Check if we have valid numbers
if [[ -z "$PROCESSED" || -z "$TOTAL" || -z "$PERCENT" ]]; then
    echo -e "${RED}Error: Could not retrieve progress data${NC}"
    exit 1
fi

# Calculate progress
REMAINING=$((TOTAL - PROCESSED))
TARGET_COUNT=$(echo "$TOTAL * $TARGET / 100" | bc)
TARGET_COUNT=${TARGET_COUNT%.*}
REMAINING_TO_TARGET=$((TARGET_COUNT - PROCESSED))

# Format progress bar (50 chars wide)
PROGRESS_WIDTH=50
FILLED_WIDTH=$(echo "$PROGRESS_WIDTH * $PROCESSED / $TOTAL" | bc)
FILLED_WIDTH=${FILLED_WIDTH%.*}
TARGET_WIDTH=$(echo "$PROGRESS_WIDTH * $TARGET / 100" | bc)
TARGET_WIDTH=${TARGET_WIDTH%.*}

# Create progress bar
PROGRESS_BAR=""
for ((i=0; i<$PROGRESS_WIDTH; i++)); do
    if [ $i -lt $FILLED_WIDTH ]; then
        PROGRESS_BAR="${PROGRESS_BAR}█"
    elif [ $i -eq $FILLED_WIDTH ]; then
        PROGRESS_BAR="${PROGRESS_BAR}▓"
    elif [ $i -lt $TARGET_WIDTH ]; then
        PROGRESS_BAR="${PROGRESS_BAR}▒"
    else
        PROGRESS_BAR="${PROGRESS_BAR}░"
    fi
done

# Output current status
echo -e "Current progress:  ${GREEN}${PERCENT}%${NC} (${PROCESSED}/${TOTAL} chunks)"
echo -e "Target:            ${YELLOW}${TARGET}%${NC} (${TARGET_COUNT}/${TOTAL} chunks)"
echo -e "Remaining to target: ${REMAINING_TO_TARGET} chunks"
echo -e "${PROGRESS_BAR} "

# Get rate of processing (if running)
if [ -f "improved_processor.log" ]; then
    # Extract processing rate from logs (chunks per hour)
    RECENT_RATE=$(tail -n 100 improved_processor.log | grep "chunks per hour" | tail -n 1 | grep -o "[0-9.]\+ chunks per hour" | cut -d' ' -f1)
    
    if [[ ! -z "$RECENT_RATE" ]]; then
        # Calculate estimated time to completion
        HOURS_TO_TARGET=$(echo "scale=1; $REMAINING_TO_TARGET / $RECENT_RATE" | bc)
        
        echo -e "Current rate:       ${GREEN}${RECENT_RATE} chunks/hour${NC}"
        echo -e "Estimated time to target: ${YELLOW}${HOURS_TO_TARGET} hours${NC}"
        
        # Convert to days+hours if more than 24 hours
        if (( $(echo "$HOURS_TO_TARGET > 24" | bc -l) )); then
            DAYS=$(echo "$HOURS_TO_TARGET / 24" | bc)
            REMAINING_HOURS=$(echo "scale=1; $HOURS_TO_TARGET - ($DAYS * 24)" | bc)
            echo -e "                   (approximately ${DAYS} days, ${REMAINING_HOURS} hours)"
        fi
    else
        echo "Processing rate:    Not available (check processor is running)"
    fi
else
    echo "Processing rate:    Log file not found (processor not started?)"
fi

# Check if processor is running
PID=$(pgrep -f "python process_to_50_percent.py" || echo "")
if [ -z "$PID" ]; then
    echo -e "${RED}Processor is not running${NC}"
else
    echo -e "${GREEN}Processor is running (PID: $PID)${NC}"
    
    # Show running time
    if [ -f "improved_processor.log" ]; then
        START_TIME=$(head -n 20 improved_processor.log | grep "started at" | head -n 1 | grep -o "[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\} [0-9]\{2\}:[0-9]\{2\}:[0-9]\{2\}")
        if [ ! -z "$START_TIME" ]; then
            START_TIMESTAMP=$(date -d "$START_TIME" +%s)
            CURRENT_TIMESTAMP=$(date +%s)
            RUNTIME_SECONDS=$((CURRENT_TIMESTAMP - START_TIMESTAMP))
            
            # Convert to hours and minutes
            RUNTIME_HOURS=$((RUNTIME_SECONDS / 3600))
            RUNTIME_MINUTES=$(((RUNTIME_SECONDS % 3600) / 60))
            
            echo -e "Running time:      ${YELLOW}${RUNTIME_HOURS}h ${RUNTIME_MINUTES}m${NC}"
        fi
    fi
fi

echo "======================================"

# Show completion status
if (( $(echo "$PERCENT >= $TARGET" | bc -l) )); then
    echo -e "${GREEN}${BOLD}Target reached!${NC} Current progress ($PERCENT%) exceeds target ($TARGET%)"
else
    PROGRESS_TO_TARGET=$(echo "scale=1; 100 * $PROCESSED / $TARGET_COUNT" | bc)
    echo -e "Progress to target: ${YELLOW}${PROGRESS_TO_TARGET}%${NC} of the way to $TARGET%"
fi