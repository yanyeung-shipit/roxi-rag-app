#!/bin/bash
# Process just a few chunks at a time to avoid timeouts
# This script is designed to be run multiple times to reach the target

# Configuration
CHUNKS_PER_RUN=5
LOG_FILE="process_chunks_incremental.log"

# Echo with timestamp function
timestamp() {
  date +"%Y-%m-%d %H:%M:%S"
}

# Check current progress
echo "$(timestamp) Starting incremental chunk processing" >> $LOG_FILE
echo "$(timestamp) Current progress:" >> $LOG_FILE
python check_progress.py >> $LOG_FILE 2>&1

# Extract current progress percentage
current_percentage=$(grep "complete" $LOG_FILE | tail -1 | awk '{print $2}' | sed 's/%//')
echo "$(timestamp) Current progress: $current_percentage%" >> $LOG_FILE

# Process a few chunks
echo "$(timestamp) Processing $CHUNKS_PER_RUN chunks" >> $LOG_FILE
python add_single_chunk.py --max-chunks $CHUNKS_PER_RUN >> $LOG_FILE 2>&1

# Check progress after processing
echo "$(timestamp) Progress after processing:" >> $LOG_FILE
python check_progress.py >> $LOG_FILE 2>&1

# Extract new progress percentage
new_percentage=$(grep "complete" $LOG_FILE | tail -1 | awk '{print $2}' | sed 's/%//')
echo "$(timestamp) New progress: $new_percentage%" >> $LOG_FILE

echo "Processed $CHUNKS_PER_RUN chunks. Current progress: $new_percentage%"
echo "Run this script again to process more chunks."