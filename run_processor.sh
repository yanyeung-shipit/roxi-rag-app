#!/bin/bash

# Exit on error
set -e

echo "Starting simple chunk processor..."
echo "Logging to: processor.log"

# Run in the foreground with output to a log file
python simple_chunk_processor.py --target 40 --delay 3 > processor.log 2>&1