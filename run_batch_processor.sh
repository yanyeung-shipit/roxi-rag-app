#!/bin/bash

# This script is a convenience wrapper that runs the preferred 
# batch processor from the processors directory

echo "ROXI Vector Store Batch Processor"
echo "=================================="
echo ""
echo "This script will run the most reliable batch processor"
echo "to process document chunks up to 40% completion."
echo ""
echo "Running processors/run_batch_to_40_percent.sh..."
echo ""

# Make it executable first (just in case)
chmod +x processors/run_batch_to_40_percent.sh

# Run the processor
./processors/run_batch_to_40_percent.sh