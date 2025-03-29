# ROXI Vector Store Processing Guide

This guide explains how to efficiently process and rebuild the vector store in the ROXI system. The vector store is a critical component that enables semantic search functionality across the knowledge base.

## Current Status

As of March 29, 2025:
- 1,261 total document chunks exist in the database across 23 documents
- ~42.8% of these chunks (540) have been processed and added to the vector store
- ~721 chunks remain to be processed

## Processing Methods

### Single Chunk Processing

For reliable, one-at-a-time processing:

```bash
./process_single_chunk.sh [chunk_id]
```

Example:
```bash
./process_single_chunk.sh 6694
```

### Multi-Chunk Processing

To process multiple chunks in sequence:

```bash
./process_n_chunks.sh [starting_chunk_id] [number_of_chunks]
```

Example (process 30 chunks starting at ID 6695):
```bash
./process_n_chunks.sh 6695 30
```

### Target Percentage Processing

To process chunks until reaching a specific completion percentage:

```bash
./process_to_target.sh [target_percentage] [start_chunk_id] [max_chunks]
```

Example (process until 65% complete):
```bash
./process_to_target.sh 65.0 6725 200
```

### Background Processing

For long-running processing that continues even if your connection drops:

```bash
./background_process_to_target.sh [target_percentage] [start_chunk_id] [max_chunks]
```

Example:
```bash
./background_process_to_target.sh 65.0 6725 200
```

To check the progress of background processing:

```bash
./check_target_progress.sh
```

## Monitoring Progress

Check the current status of the vector store:

```bash
python check_progress.py
```

For detailed progress with time estimates and completion rates.

## Tips for Efficient Processing

1. **Incremental Processing**: Process chunks in small batches (20-30 at a time) to avoid timeouts
2. **Background Processing**: For longer batches, use the background scripts
3. **Regular Monitoring**: Check progress to ensure processing is continuing as expected
4. **Handling Failures**: If a chunk fails to process, skip it and continue with the next one
5. **Resource Consideration**: Processing is resource-intensive; limit concurrent processes

## Troubleshooting

If processing appears to stall:

1. Check for running processes with `ps aux | grep process`
2. Look for log files in `logs/batch_processing/` directory
3. If a process has terminated unexpectedly, check for and remove stale PID files
4. If the vector store seems corrupted, consider using the rebuild scripts in the repository

## Next Steps

1. Continue processing chunks until reaching at least 65% completion
2. Monitor system performance during and after processing
3. Verify search quality improves as more chunks are added to the vector store