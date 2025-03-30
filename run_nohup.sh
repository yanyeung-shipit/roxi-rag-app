#!/bin/bash

# Exit on error
set -e

echo "Starting simple chunk processor with nohup..."
nohup python simple_chunk_processor.py --target 40 --delay 3 > nohup_processor.log 2>&1 &
echo "Process started with PID: $!"
echo "Logging to: nohup_processor.log"