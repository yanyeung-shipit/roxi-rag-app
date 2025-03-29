# Batch Processing Guide

This guide explains how to use the batch processing tools to process chunks incrementally and add them to the vector store.

## Background

The vector store needs to be populated with embeddings for all the chunks in the database. This is a time-consuming process, but it can be done incrementally. The scripts in this guide are designed to process chunks in a reliable way, avoiding timeouts and errors.

## Quick Start

Process chunks one at a time (most reliable method):
```
./process_single_chunk.sh 6683  # Replace with the next chunk ID to process
```

Process a small batch of chunks (5 by default):
```
./process_multiple_chunks.sh 6682 5  # Replace first number with the last processed chunk ID
```

Get the next chunks that need to be processed:
```
python get_next_chunks.py 6682 --limit 10  # Replace with the last processed chunk ID
```

Check the current progress:
```
python check_progress.py
```

## Script Details

### `process_single_chunk.sh`

This script processes a single chunk and adds it to the vector store.

**Usage:**
```
./process_single_chunk.sh CHUNK_ID
```

**Example:**
```
./process_single_chunk.sh 6683
```

### `process_multiple_chunks.sh`

This script processes multiple chunks in sequence, one at a time. It's designed to be more reliable than batch processing by handling each chunk individually.

**Usage:**
```
./process_multiple_chunks.sh LAST_ID BATCH_SIZE
```

**Example:**
```
./process_multiple_chunks.sh 6682 10
```

### `get_next_chunks.py`

This script gets the next chunks to process after a given ID.

**Usage:**
```
python get_next_chunks.py LAST_ID [--limit LIMIT]
```

**Example:**
```
python get_next_chunks.py 6682 --limit 5
```

### `check_progress.py`

This script checks the current progress of rebuilding the vector store.

**Usage:**
```
python check_progress.py
```

## Workflow

A typical workflow would be:

1. Check the current progress to see which chunks are already processed:
   ```
   python check_progress.py
   ```

2. Get the next batch of chunks to process:
   ```
   python get_next_chunks.py LAST_ID --limit 10
   ```

3. Process each chunk one at a time:
   ```
   ./process_single_chunk.sh CHUNK_ID
   ```
   
   Or process a small batch at once:
   ```
   ./process_multiple_chunks.sh LAST_ID 5
   ```

4. Check the progress again to confirm the chunks were added:
   ```
   python check_progress.py
   ```

## Tips

- Processing one chunk at a time is the most reliable method in the Replit environment
- Each chunk takes approximately 1-1.5 seconds to process
- Logs are stored in the `logs/batch_processing` directory
- If a script times out, you can safely run it again with the next chunk ID
- Don't run multiple processing scripts at the same time to avoid conflicts