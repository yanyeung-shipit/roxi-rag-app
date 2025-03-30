# Batch Processing Guide

This guide explains how batch processing works in the ROXI system and provides instructions for using the various batch processing tools.

## Introduction

Batch processing in ROXI allows for efficient processing of large numbers of document chunks in a controlled and optimized manner. Instead of processing each chunk individually, which would incur overhead for each operation, batch processing groups chunks together for more efficient handling.

## Available Batch Processing Tools

### 1. `process_chunks_until_50_percent.py`

This is our primary batch processing script that will continue running until 50% of all document chunks have been processed.

```bash
# Run directly
python process_chunks_until_50_percent.py

# Run in background
nohup python process_chunks_until_50_percent.py > processing_50_continuous.log 2>&1 &
```

Features:
- Processes documents in configurable batch sizes
- Handles its own error recovery
- Creates periodic backups
- Provides detailed logging
- Will exit when the 50% target is reached

### 2. `batch_process_chunks.py`

Processes a specific number of chunks in a single run.

```bash
# Process 10 chunks
python batch_process_chunks.py --num-chunks=10
```

### 3. `batch_rebuild_to_target.py`

Advanced batch processor that rebuilds the vector store to a target percentage.

```bash
# Process until 75% complete with batches of 10
python batch_rebuild_to_target.py --target=75 --batch-size=10
```

## Monitoring Batch Processing

### Progress Checking

Use these tools to monitor the progress of batch processing:

```bash
# Simple progress check
./check_50_percent_progress.sh

# Continuous monitoring with notification
./check_and_notify_50_percent.sh

# Comprehensive monitoring with backups
./monitor_and_backup.sh
```

### Log Files

The batch processing scripts create detailed logs:

- `process_until_50_percent.log`: Main processing log
- `notify_50_percent.log`: Notification script log
- `logs/monitor_YYYYMMDD.log`: Daily monitoring logs

## Batch Processing Parameters

These parameters can be adjusted in the scripts:

- **Batch Size**: Number of chunks to process at once (default: 5)
- **Retry Limit**: Maximum number of retries for failed chunks (default: 3) 
- **Backup Interval**: Number of batches between backups (default: 10)
- **Delay Between Batches**: Seconds to wait between batches (default: 1)

## Best Practices

1. **Start with a backup**: Always create a backup before starting batch processing
2. **Use reasonable batch sizes**: 5-10 chunks per batch is usually optimal
3. **Monitor memory usage**: Watch for excessive memory consumption
4. **Keep logs for troubleshooting**: Don't delete logs until processing is complete
5. **Schedule during low-usage periods**: Batch processing is resource-intensive

## Common Issues and Solutions

### Processing is too slow

- Reduce batch size
- Check API rate limits
- Ensure the system isn't running other resource-intensive tasks

### Memory usage is too high

- Reduce batch size
- Ensure deep sleep mode is working correctly
- Check for memory leaks in processing code

### Errors during processing

- Check logs for specific error messages
- Verify the OpenAI API key is valid
- Ensure database connections are working properly

## Advanced Batch Processing

For more advanced batch processing needs:

- `enhanced_rebuild.py`: Complete vector store rebuild with advanced recovery
- `find_unprocessed_chunks.py`: Identify chunks that haven't been processed yet
- `direct_process_chunk.py`: Process specific chunks by ID