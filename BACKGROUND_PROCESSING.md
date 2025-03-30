# Background Processing System Documentation

This document explains how the background processing system works in ROXI, including how to monitor it, manage it, and recover from issues.

## Overview

ROXI uses a sophisticated background processing system to handle the embedding and indexing of document chunks. This system is designed to:

1. Process documents incrementally to avoid memory issues
2. Adapt to system load by pausing during high-load periods
3. Conserve resources during idle periods with "deep sleep" mode
4. Recover automatically from errors and crashes
5. Provide detailed monitoring and progress tracking

## Key Components

### 1. Continuous Processor

The `continuous_rebuild.py` script is the core of the background processing system. It runs continuously in the background, processing unprocessed document chunks in the database.

Key features:
- Robust error handling (individual document failures don't stop the entire process)
- Checkpoint-based recovery system
- Adaptive sleep with deep sleep mode for resource conservation
- Comprehensive monitoring and progress tracking

### 2. Target-Based Processors

Several target-based processors are available to process chunks until reaching a specific percentage:

- `process_to_50_percent.py` - Process until 50% of chunks are complete
- `batch_rebuild_to_target.py` - Configurable target percentage

### 3. Monitoring System

Several tools are available to monitor the processing:

- `check_progress.py` - General progress check
- `check_50_percent_progress.sh` - Visual progress toward 50% goal
- `monitor_vector_store.py` - Continuous monitoring for data integrity
- `monitor_and_backup.sh` - Combined monitoring and backup system

### 4. Backup System

The system includes an automated backup system to prevent data loss:

- `backup_vector_store.py` - Creates timestamped backups
- `schedule_backups.sh` - Schedules regular backups
- `monitor_and_backup.sh` - Combines monitoring and backup functions

## Deep Sleep Mode

To conserve system resources during idle periods, the background processor enters "deep sleep" mode. This mode:

1. Unloads the vector store from memory (7-stage cleanup)
2. Releases memory back to the OS
3. Sets embedding cache parameters to minimal values
4. Checks for new work less frequently
5. Can be manually triggered via the "Force Deep Sleep" button

The processor automatically exits deep sleep mode when new documents are added.

## Memory Optimization

The system employs several memory optimization techniques:

1. Using float16 embeddings to reduce memory footprint by ~50%
2. Incremental processing to avoid loading all documents at once
3. Unloading vector store when not in use
4. OS-level memory release through malloc_trim on Linux
5. Minimal embedding cache parameters in deep sleep mode

## Usage Instructions

### Running the Processor

To start processing in the background:

```bash
python continuous_rebuild.py
```

To process to a specific target (e.g., 50%):

```bash
python process_to_50_percent.py
```

### Monitoring Progress

To check current progress:

```bash
python check_progress.py
# or
./check_50_percent_progress.sh
```

### Setting Up Automated Protection

To set up combined monitoring and backups:

```bash
./monitor_and_backup.sh
```

This will:
- Monitor the vector store for data loss
- Create backups every 4 hours
- Automatically recover if problems are detected

## Recovery Procedures

If data loss is detected:

1. Check the latest backups in `./backups/daily/`
2. Restore the most recent backup:
   ```bash
   cp ./backups/daily/TIMESTAMP_document_data.pkl ./document_data.pkl
   cp ./backups/daily/TIMESTAMP_faiss_index.bin ./faiss_index.bin
   ```
3. Restart the background processor

## Troubleshooting

**Problem: Processor not running**
- Check for Python errors in the logs
- Ensure database is accessible
- Verify OpenAI API key is valid

**Problem: Processing too slow**
- Check for API rate limiting
- Monitor system resources for bottlenecks
- Consider batch processing with `batch_rebuild_to_target.py`

**Problem: High memory usage**
- Force deep sleep mode when not actively using the system
- Check if other processes are consuming memory
- Reduce batch size in batch processors

## Internal Architecture

The background processor uses a multi-stage pipeline:

1. **Selection**: Identify unprocessed chunks in the database
2. **Processing**: Generate embeddings for each chunk
3. **Indexing**: Add embeddings to the vector store
4. **Verification**: Verify chunks were correctly added
5. **Cleanup**: Release resources no longer needed

## Log Files

- `improved_processor.log` - Main processor log
- `monitor.log` - Vector store monitor log
- `backup_vector_store.log` - Backup system log