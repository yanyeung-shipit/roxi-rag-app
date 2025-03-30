#!/bin/bash

# This script is a convenience wrapper that runs the preferred 
# processor from the processors directory

echo "ROXI Vector Store Processor"
echo "==========================="
echo ""
echo "This script will run the most advanced processor"
echo "to process document chunks efficiently."
echo ""
echo "Using the adaptive processor that automatically"
echo "adjusts to available system resources."
echo ""

# Make it executable first (just in case)
chmod +x run_adaptive_processor.sh

# Run the adaptive processor
./run_adaptive_processor.sh