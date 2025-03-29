#!/bin/bash

# process_two_chunks.sh
# This script processes exactly two chunks for the vector store rebuild process
# It's designed to be less likely to time out

echo "Starting two-chunk processing at $(date)"
echo "-----------------------------------------"

# Process first chunk
echo "Processing chunk 1 of 2..."
python add_single_chunk.py

# Process second chunk
echo "Processing chunk 2 of 2..."
python add_single_chunk.py

echo "-----------------------------------------"
echo "Two-chunk processing completed at $(date)"