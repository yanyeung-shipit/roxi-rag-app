# Legacy Scripts

This directory contains scripts that have been moved from the main directory to reduce clutter.
These scripts are preserved for reference but are considered redundant with other scripts in the system.

Scripts were moved on: 2025-03-30 21:23:22

## Replacement Guide

| Legacy Script | Replacement |
|---------------|-------------|
| simple_chunk_processor.py | add_single_chunk.py |
| process_multiple_direct.py | batch_process_chunks.py |
| run_chunk_processor.py | processors/run_batch_to_40_percent.sh |
| process_one_chunk.py | add_single_chunk.py |
| process_next_ten.py | batch_process_chunks.py |
| test_process_for_5min.py | (Testing script only) |
| simplified_processor.py | adaptive_processor.py |

## Recommended Processors

The following processors are recommended for most uses:

1. processors/adaptive_processor.py - Resource-adaptive processing
2. batch_rebuild_to_target.py - Fast batch processing
3. add_single_chunk.py - Reliable single-chunk processing

For database connection issues, use enhanced_batch_processor.py.
