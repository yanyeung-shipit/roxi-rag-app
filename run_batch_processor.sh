#!/bin/bash

# run_batch_processor.sh
# Process multiple chunks in a single batch efficiently

# Process 5 chunks by default, but allow overriding via command-line argument
NUM_CHUNKS=${1:-5}

echo "======================================================"
echo "BATCH PROCESSING $NUM_CHUNKS CHUNKS"
echo "======================================================"
echo "Starting at: $(date)"
echo "======================================================"

# Make the script executable
chmod +x batch_process_chunks.py

# Run the batch processor
python batch_process_chunks.py --num-chunks $NUM_CHUNKS

# Check the result
RESULT=$?
if [ $RESULT -eq 0 ]; then
    echo "✅ Batch processing completed successfully"
else
    echo "❌ Batch processing failed with exit code $RESULT"
fi

echo "Completed at: $(date)"
echo "======================================================"