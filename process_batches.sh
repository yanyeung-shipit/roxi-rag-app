#!/bin/bash
# Enhanced script to process vector store rebuilding in batches with monitoring and control
# Usage: ./process_batches.sh [batch_size] [delay] [show_progress]

# Default values - can be overridden by passing arguments
BATCH_SIZE=${1:-50}
DELAY_BETWEEN_CHUNKS=${2:-1} # seconds to wait between chunks
SHOW_PROGRESS=${3:-true}

# Create log directory if it doesn't exist
mkdir -p logs

# Create a timestamp for the log files
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="logs/rebuild_${TIMESTAMP}.log"

# Set environment variable for python path
export PYTHONPATH=.

echo "Starting vector store rebuild process..."
echo "Batch size: $BATCH_SIZE chunks"
echo "Delay between chunks: $DELAY_BETWEEN_CHUNKS seconds"
echo "Show progress: $SHOW_PROGRESS"
echo "Log file: $LOG_FILE"
echo ""

# Initial progress check
echo "========== INITIAL STATE ==========" | tee -a "$LOG_FILE"
python check_progress.py | tee -a "$LOG_FILE"
INITIAL_VECTOR_CHUNKS=$(python -c "from utils.vector_store import VectorStore; store = VectorStore(); stats = store.get_stats(); print(stats.get('total_documents', 0))")
echo "Initial vector chunks: $INITIAL_VECTOR_CHUNKS" | tee -a "$LOG_FILE"
echo ""

# Process chunks
echo "========== PROCESSING CHUNKS ==========" | tee -a "$LOG_FILE"
for i in $(seq 1 $BATCH_SIZE); do
  echo "Processing chunk $i of $BATCH_SIZE..." | tee -a "$LOG_FILE"
  
  # Process one chunk and capture any errors
  python add_single_chunk.py >> "$LOG_FILE" 2>&1
  
  # Check for errors
  if [ $? -ne 0 ]; then
    echo "Error processing chunk $i. Check $LOG_FILE for details." | tee -a "$LOG_FILE"
    echo "Continuing with next chunk..."
  fi
  
  # Show current progress if enabled
  if $SHOW_PROGRESS; then
    echo "Current vector store status:" | tee -a "$LOG_FILE"
    python -c "from utils.vector_store import VectorStore; store = VectorStore(); stats = store.get_stats(); print(f'Vector store statistics: {stats}')" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
  fi
  
  # Check if we should run a full progress check every 10 chunks
  if [ $((i % 10)) -eq 0 ]; then
    echo "Progress check at chunk $i:" | tee -a "$LOG_FILE"
    python check_progress.py | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
  fi
  
  # Sleep briefly to avoid rate limits
  sleep $DELAY_BETWEEN_CHUNKS
done

# Final progress check
echo "========== FINAL STATE ==========" | tee -a "$LOG_FILE"
python check_progress.py | tee -a "$LOG_FILE"
FINAL_VECTOR_CHUNKS=$(python -c "from utils.vector_store import VectorStore; store = VectorStore(); stats = store.get_stats(); print(stats.get('total_documents', 0))")
echo "Final vector chunks: $FINAL_VECTOR_CHUNKS" | tee -a "$LOG_FILE"
echo ""

# Calculate how many chunks were processed
CHUNKS_PROCESSED=$((FINAL_VECTOR_CHUNKS - INITIAL_VECTOR_CHUNKS))
echo "Batch complete!" | tee -a "$LOG_FILE"
echo "Processed $CHUNKS_PROCESSED new chunks in this batch." | tee -a "$LOG_FILE"
echo "See $LOG_FILE for complete log." | tee -a "$LOG_FILE"

# Check if we're complete
TOTAL_DB_CHUNKS=$(python -c "from check_progress import check_progress; result = check_progress(); print(result['db_chunks'])")
if [ "$FINAL_VECTOR_CHUNKS" -ge "$TOTAL_DB_CHUNKS" ]; then
  echo "Vector store rebuild is COMPLETE! All $TOTAL_DB_CHUNKS chunks have been processed." | tee -a "$LOG_FILE"
else
  REMAINING=$((TOTAL_DB_CHUNKS - FINAL_VECTOR_CHUNKS))
  PERCENT_COMPLETE=$(awk "BEGIN {printf \"%.1f\", ($FINAL_VECTOR_CHUNKS / $TOTAL_DB_CHUNKS) * 100}")
  echo "Vector store rebuild is $PERCENT_COMPLETE% complete. $REMAINING chunks remaining." | tee -a "$LOG_FILE"
fi