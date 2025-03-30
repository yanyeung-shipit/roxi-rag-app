#!/bin/bash

# Start the process to reach 50% completion
python process_to_50_percent.py > processing.log 2>&1 &

echo "Started processing script to reach 50% completion"
echo "View logs with: tail -f processing.log"