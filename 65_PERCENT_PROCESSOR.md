# 65% Vector Store Processor

This tool processes chunks from the database and adds them to the vector store until 65% of all chunks have been processed. It's designed to be reliable, efficient, and to automatically handle errors with retries.

## Overview

The 65% processor works by:

1. Querying the database for unprocessed chunks
2. Generating embeddings for these chunks using OpenAI's API
3. Adding the embeddings to the vector store
4. Saving progress to disk after each chunk
5. Continuing until 65% of all chunks are processed

## Usage

### Starting the Processor

To start the processor with default settings (batch size 5, target 65%):

```bash
./run_65_percent_processor.sh
```

This script will:
- Clean up any existing (but non-running) processor processes
- Start the processor in the background
- Monitor progress
- Automatically restart the processor if it crashes
- Stop once the target percentage is reached

### Checking Progress

To check the current progress of the processor:

```bash
python check_processor_progress.py
```

For JSON output (useful for automated systems):

```bash
python check_processor_progress.py --json
```

To change the target percentage (for reporting purposes only):

```bash
python check_processor_progress.py --target 70.0
```

### Stopping the Processor

To gracefully stop the processor before it reaches its target:

```bash
# Find the PID
cat process_to_65_percent.pid

# Send a termination signal
kill -15 [PID]
```

## Monitoring and Debugging

### Log Files

- `process_to_65_percent_service.log`: Main processor log
- `process_to_65_percent.pid`: Contains the PID of the running processor

### Common Issues

1. **Rate Limiting**: If you encounter OpenAI API rate limits, the processor will automatically retry with exponential backoff.

2. **Duplicate Chunk Processing**: The processor includes safeguards to ensure each chunk is processed only once, even if database queries return the same chunk multiple times.

3. **Orphaned PID Files**: If the processor crashes without cleaning up its PID file, the run script will handle this gracefully on the next start.

## Technical Details

- Uses float16 embeddings to reduce memory footprint
- Implements proper signal handling for graceful shutdown
- Manages database connection pooling efficiently
- Automatically adds chunk and document IDs to metadata
- Validates that chunks are properly added to vector store

## Requirements

- Python 3.9+
- OpenAI API key in environment variables
- PostreSQL database with database credentials in environment variables