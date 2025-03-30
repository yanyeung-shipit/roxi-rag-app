# Background Processing Guide

This guide explains how the background processing system works in the ROXI (Rheumatology Optimized eXpert Intelligence) system.

## Overview

ROXI's background processing system manages the resource-intensive task of embedding document chunks into the vector store. This process converts raw text into high-dimensional vector representations that enable semantic search capabilities.

## Key Components

### 1. Vector Store

The vector store is responsible for:
- Storing document embeddings
- Managing the FAISS index for similarity search
- Saving and loading the vector database from disk
- Memory management (including deep sleep mode)

### 2. Background Processor

The background processor:
- Runs as a separate thread in the application
- Processes documents in the queue
- Adapts its activity based on system usage patterns
- Enters deep sleep mode during periods of inactivity

### 3. Processing Scripts

Several scripts are available for different processing needs:

- `process_chunks_until_50_percent.py`: Processes chunks until 50% of the database is complete
- `check_50_percent_progress.sh`: Checks current progress toward 50% completion
- `check_and_notify_50_percent.sh`: Monitors and notifies when 50% target is reached
- `monitor_and_backup.sh`: Monitors processing and creates regular backups
- `backup_vector_store.py`: Creates backups of the vector store

## Resource Management

The system includes sophisticated resource management:

### Deep Sleep Mode

When the system is inactive, the background processor enters deep sleep mode:

1. The vector store is completely unloaded from memory
2. All caches are cleared
3. Memory is released back to the operating system
4. Embedding services are suspended
5. The processor only wakes up periodically to check for new documents

This dramatically reduces memory usage during inactive periods while ensuring the system remains responsive when needed.

### Memory Optimization

Several memory optimization techniques are employed:

- Using float16 embeddings (half-precision) to reduce memory footprint
- Progressive loading of documents when performing searches
- Caching with intelligent expiration
- Periodic garbage collection
- OS-level memory release via malloc_trim on Linux

## Processing Workflow

1. Documents are uploaded and stored in the database
2. Each document is split into manageable chunks
3. Processing scripts convert chunks to vector embeddings
4. Chunks are added to the vector store with metadata
5. Regular backups preserve progress
6. Progress monitoring tracks completion percentage

## Monitoring and Maintenance

To monitor processing status:

```bash
# Check current progress
./check_50_percent_progress.sh

# Monitor progress with notifications
./check_and_notify_50_percent.sh

# Monitor with backups
./monitor_and_backup.sh
```

## Performance Considerations

- Processing speed depends on API rate limits and system resources
- The system is designed to process in batches to optimize throughput
- Backups are created regularly to prevent data loss
- The system can be paused and resumed without losing progress

## Best Practices

1. Allow the system to reach the 50% threshold before heavy usage
2. Create regular backups during processing
3. Monitor memory usage with the system resources card
4. Use deep sleep mode when the system will be inactive for extended periods