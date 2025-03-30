# ROXI Processing Scripts Reference Guide

*Generated on: 2025-03-30 21:13:29*

This document serves as a central reference for all processing scripts in the ROXI system. It categorizes scripts by functionality and provides information about when to use each one.

## PRIMARY RECOMMENDED PROCESSORS

| Script | Purpose | When to Use | Special Features |
|--------|---------|-------------|-----------------|
| **processors/adaptive_processor.py** | Adaptive Document Processor | **DEFAULT CHOICE** for most scenarios | Auto-adjusts batch size, deep sleep mode |

## DATABASE CONNECTION HANDLING

| Script | Purpose | When to Use | Special Features |
|--------|---------|-------------|-----------------|
| robust_process_to_50_percent.py | Robust Process to 50% Target | If PostgreSQL SSL connection errors occur |  |
| enhanced_batch_processor.py | Enhanced Batch Processor with Robust Database Connection Handling | If PostgreSQL SSL connection errors occur | Uses VectorStore add_embedding method for adding chunks |
| enhanced_process_to_50_percent.py | Enhanced Processing to 50 Percent | If PostgreSQL SSL connection errors occur |  |
| enhanced_process_to_65_percent.py | Enhanced Processing to 65 Percent | **RECOMMENDED** for reaching 65% target during SSL errors | Most recent version with improved field handling |

## MONITORING AND MANAGEMENT SCRIPTS

| Script | Purpose | When to Use | Special Features |
|--------|---------|-------------|-----------------|
| check_processor_progress.py | Script to check the progress of the vector store rebuilding process. | For continuous process supervision |  |
| check_and_restart_processor.sh | !/bin/bash | For continuous process supervision |  |
| monitor_and_restart.sh | !/bin/bash | For continuous process supervision |  |
| enhanced_monitor_and_restart.sh | !/bin/bash | For continuous process supervision |  |

## SPECIALIZED PROCESSING SCRIPTS

| Script | Purpose | When to Use | Special Features |
|--------|---------|-------------|-----------------|
| direct_process_chunk.py | Direct and simplified chunk processor - optimized for directly processing a specific chunk ID |  |  |
| parallel_chunk_processor.py | Parallel Chunk Processor |  |  |
| process_to_sixty_six_percent.py | Process chunks using the batch processor until we reach 66% completion. |  |  |
| fast_chunk_processor.py | Fast Chunk Processor - Optimized for Replit environment |  |  |
| process_to_75_percent.py | Script to process chunks until 75% completion. |  |  |
| process_to_50_percent.py | Process to 50% Target |  |  |

## LEGACY/REDUNDANT SCRIPTS

| Script | Replaced By | Notes |
|--------|-------------|-------|
| **process_multiple_direct.py** | batch_process_chunks.py | Process multiple chunks in sequence using direct_process_chunk.py |
| **process_next_ten.py** | batch_process_chunks.py | Simple script to process the next 10 chunks in sequence. |
| **process_one_chunk.py** | add_single_chunk.py | Process a single chunk identified by find_unprocessed_chunks.py. |
| **run_chunk_processor.py** | processors/run_batch_to_40_percent.sh | Run Chunk Processor - Continuous Background Processing Script |
| **simple_chunk_processor.py** | add_single_chunk.py | Simple, direct chunk processor for adding documents to vector store. |
| **simplified_processor.py** | adaptive_processor.py | Super simplified processor for adding documents to vector store. |
| **test_process_for_5min.py** | N/A - testing script only | Test the processing script for 5 minutes to verify it works correctly. |

## OTHER SCRIPTS

| Script | Description |
|--------|-------------|
| batch_process_chunks.py | Batch process multiple chunks efficiently. |
| fast_process_chunk.py | Fast chunk processor optimized for speed. |
| find_unprocessed_chunks.py | Find unprocessed chunks by comparing database chunks to vector store. |
| improved_continuous_processor.py | Improved Continuous Processor |
| manage_processors.py | Script Management Tool for ROXI |
| monitor_and_backup.sh | !/bin/bash |
| monitor_progress.sh | !/bin/bash |
| process_chunk.py | Process a single chunk by ID and add it to the vector store. |
| process_chunks_background.py | Background Chunk Processing Script |
| process_chunks_to_66_percent.py | Process chunks incrementally until we reach 66% completion. |
| process_chunks_until_50_percent.py | Script to process chunks until reaching 50% completion. |
| process_until_target.py | Process chunks until a target percentage is reached. |
| resilient_processor.py | Resilient Chunk Processor - Enhanced for Replit Environment |
| restart_all_processors.sh | !/bin/bash |
| run_continuous_monitor.sh | !/bin/bash |
| update_processor_docs.py | Update Processor Documentation |
| utils/background_processor.py | Lazily import a module only when it's needed. |
| utils/document_processor.py | Extract citation information from the filename or PDF content. |
| utils/get_processed_chunks.py | Memory-optimized module for retrieving processed chunk IDs from the vector store. |
| utils/topic_content_processor.py | Topic content processor functions for handling rheum.reviews topic pages. |

## Best Practices

1. **Always Check the README First**: Before creating a new script, check this reference guide and the processors/README.md file.

2. **Use the adaptive_processor.py**: This is our most sophisticated processor that handles resource management and includes all essential features.

3. **Handle Database Errors**: If encountering PostgreSQL SSL connection errors, use the enhanced_batch_processor.py.

4. **Monitoring**: Always use a monitoring script when running long batch processes.

5. **Progressive Goals**: Target smaller percentages first (40-50%) before attempting larger goals (75-100%).

6. **Documentation**: When creating a new script, document it here for future reference.
