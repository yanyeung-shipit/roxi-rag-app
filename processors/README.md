# Document Processors for ROXI

This directory contains our most valuable and reliable document processors for the ROXI system. These processors handle the transformation of raw document chunks into vector embeddings for the knowledge base.

## Key Processors

### batch_rebuild_to_target.py
Our most sophisticated batch processor with the following features:
- Processes documents in configurable batch sizes
- Targets a specific completion percentage
- Includes checkpoint capabilities for resuming work
- Provides detailed progress tracking and time estimation
- Has robust error handling and retry logic

Usage:
```
python processors/batch_rebuild_to_target.py --target 40.0 --batch-size 10
```

### run_batch_to_40_percent.sh
A convenient script that runs the batch processor with optimal settings:
- Processes chunks in batches of 10
- Targets 40% completion 
- Logs progress to a timestamped file
- Creates necessary directories automatically

Usage:
```
./processors/run_batch_to_40_percent.sh
```

## Other Processors

We maintain several other processors in the main directory for different use cases:

- **add_single_chunk.py**: Processes one chunk at a time, slower but more reliable in resource-constrained environments
- **continuous_rebuild.py**: Runs continuously until all chunks are processed
- **direct_process_chunk.py**: Simplified processor for directly processing specific chunk IDs
- **fast_chunk_processor.py**: Optimized for speed but may use more resources
- **parallel_chunk_processor.py**: Attempts to process multiple chunks in parallel

## Monitoring Tools

- **check_processor_progress.py**: Check the current progress of rebuilding
- **monitor_rebuild.py**: Monitors the rebuild process and provides status updates
- **monitor_and_restart.sh**: Automatically restarts failed processes

## Best Practices

1. For bulk processing, use `batch_rebuild_to_target.py` with appropriate batch sizes
2. For overnight processing in Replit's resource-constrained environment, use single processors with monitoring
3. Always check progress with `check_processor_progress.py` before and after processing
4. Use checkpoint capabilities to resume interrupted processing