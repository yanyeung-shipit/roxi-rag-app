# Batch Processing Guide for Vector Store Rebuilding

This guide explains how to use the batch processing tools to gradually rebuild the vector store without running into Replit resource limitations.

## Overview

The system has 1,261 total document chunks in the database, but only a portion of them (approximately 35% as of March 29, 2025) have been added to the vector store with embeddings. The batch processing tools allow you to gradually process more chunks without waiting for all of them to complete at once, which would exceed Replit's resource limits.

## Available Tools

### 1. Single Batch Processor

The `process_next_batch.sh` script processes a specific number of chunks in one execution:

```bash
./process_next_batch.sh [batch_size]
```

- `batch_size`: Optional. Number of chunks to process in one batch (default: 8)

Example: `./process_next_batch.sh 5` to process 5 chunks

### 2. Continuous Processor

The `run_continuous_processor.sh` script attempts to continuously process batches of chunks until completion or until reaching a maximum number of batches:

```bash
./run_continuous_processor.sh [batch_size] [max_batches]
```

- `batch_size`: Optional. Number of chunks per batch (default: 5)
- `max_batches`: Optional. Maximum number of batches to process (default: 100)

Example: `./run_continuous_processor.sh 8 10` to process 10 batches of 8 chunks each

### 3. Progress Checker

Check the current progress at any time:

```bash
python check_progress.py
```

## Recommended Usage

### For Manual Processing

1. Run `./process_next_batch.sh 5` to process 5 chunks at a time
2. Check progress with `python check_progress.py`
3. Repeat as needed until all chunks are processed

### For Semi-Automatic Processing

1. Run `./run_continuous_processor.sh 5 20` to process up to 20 batches of 5 chunks each
2. If it times out, simply run it again to continue processing

## Logs and Monitoring

- Batch processing logs are stored in `logs/batch_processing/`
- Each log file is named with a timestamp (e.g., `batch_20250329_214143.log`)
- These logs contain detailed information about each batch processing run

## Processing Speed and Performance

- Each chunk takes approximately 0.4-0.8 seconds to process
- Batch processing is significantly more efficient than processing chunks one at a time
- The system automatically handles errors and timeouts gracefully
- Estimated completion time for all chunks is displayed after each progress check

## Background Information

- The vector store contains embeddings for document chunks, which are used for semantic search
- Each chunk must exist in both the database AND the vector store to be searchable
- The batch processing ensures that chunks are properly added to the vector store with embeddings
- Once all chunks are processed, the system will have complete searchability across all documents