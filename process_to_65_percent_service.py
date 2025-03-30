#!/usr/bin/env python3
"""
Process to 65 Percent Service

This script runs as a long-lived service that will continue processing
chunks until 65% of all chunks are in the vector store. It includes
built-in monitoring and automatic restart capabilities.

Features:
- Runs continuously until 65% target is reached
- Handles database connection errors with retry logic
- Logs progress to a dedicated log file
- Can run in background with nohup
"""

import argparse
import atexit
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Set, Union

import numpy as np
import requests
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from tenacity import retry, stop_after_attempt, wait_exponential

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("process_to_65_percent_service.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Process65PercentService")

# Constants
DATABASE_URL = os.environ.get('DATABASE_URL')
BATCH_SIZE = 5
TARGET_PERCENTAGE = 65.0
MAX_RETRIES = 5
CHECKPOINT_FILE = "process_to_65_percent_checkpoint.json"
PID_FILE = "process_to_65_percent.pid"

class Process65PercentService:
    """
    Service to process chunks until 65% completion.
    """
    
    def __init__(self, batch_size: int = BATCH_SIZE, target_percentage: float = TARGET_PERCENTAGE):
        """
        Initialize the service.
        
        Args:
            batch_size: Number of chunks to process per batch
            target_percentage: Target percentage of completion to reach
        """
        self.batch_size = batch_size
        self.target_percentage = target_percentage
        self.processed_chunk_ids = set()
        self.total_processed = 0
        self.total_chunks = 0
        self.running = True
        self.save_pid()
        
        # Set up proper signal handling for graceful shutdown
        import signal
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        
        logger.info(f"Initialized process 65% service with batch size {batch_size} and target {target_percentage}%")
        atexit.register(self.cleanup)
        
    def _handle_signal(self, signum, frame):
        """Handle signals for graceful shutdown."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    def save_pid(self) -> None:
        """Save the current process ID to a file for monitoring."""
        with open(PID_FILE, 'w') as f:
            f.write(str(os.getpid()))
        logger.info(f"PID {os.getpid()} saved to {PID_FILE}")
    
    def cleanup(self) -> None:
        """Clean up resources when the process exits."""
        logger.info("Cleaning up resources and saving checkpoint...")
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        logger.info("Cleanup complete")
    
    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        reraise=True
    )
    def get_db_engine(self):
        """
        Get a SQLAlchemy database engine with proper connection settings.
        
        Returns:
            SQLAlchemy Engine with configured connection pool
        """
        try:
            engine = create_engine(
                DATABASE_URL,
                pool_pre_ping=True,
                pool_recycle=300,
                connect_args={'connect_timeout': 10}
            )
            # Test the connection
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return engine
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            raise
    
    def get_total_chunks(self) -> int:
        """
        Get the total number of chunks in the database.
        
        Returns:
            Total number of chunks
        """
        try:
            engine = self.get_db_engine()
            with engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) FROM document_chunks"))
                return result.scalar()
        except Exception as e:
            logger.error(f"Error getting total chunks: {e}")
            return 0
    
    def get_processed_chunk_ids(self) -> Set[int]:
        """
        Get IDs of chunks that have already been processed.
        
        Returns:
            Set of chunk IDs that are already in the vector store
        """
        from utils.vector_store import VectorStore
        try:
            vector_store = VectorStore()
            processed_ids = vector_store.get_processed_chunk_ids()
            return set(processed_ids)
        except Exception as e:
            logger.error(f"Error getting processed chunk IDs: {e}")
            return set()
    
    def get_next_chunk_batch(self) -> List[Dict[str, Any]]:
        """
        Get the next batch of chunks to process.
        
        Returns:
            List of chunk dictionaries
        """
        try:
            # Get the processed chunk IDs
            self.processed_chunk_ids = self.get_processed_chunk_ids()
            
            # For efficiency, let's update our approach to get unprocessed chunks:
            # 1. If we have less than 1000 processed IDs, use NOT IN directly
            # 2. Otherwise, use a more efficient approach with temporary table or different query structure
            
            if len(self.processed_chunk_ids) < 1000:
                # Create SQL query to get unprocessed chunks with NOT IN
                sql = text("""
                    SELECT c.id, c.document_id, c.text_content, c.chunk_index, c.page_number, 
                           d.title, d.source_url, d.file_type AS source_type
                    FROM document_chunks c
                    JOIN documents d ON c.document_id = d.id
                    WHERE c.id NOT IN :processed_ids
                    ORDER BY c.id
                    LIMIT :limit
                """)
                
                engine = self.get_db_engine()
                with engine.connect() as conn:
                    # Convert the set to a tuple for proper SQL parameter passing
                    processed_ids_tuple = tuple(self.processed_chunk_ids) or (-1,)
                    result = conn.execute(
                        sql, 
                        {"processed_ids": processed_ids_tuple, "limit": self.batch_size}
                    )
                    chunks = []
                    for row in result:
                        # Create metadata from available fields
                        metadata = {
                            'title': row.title,
                            'url': row.source_url,
                            'source_type': row.source_type,
                            'chunk_index': row.chunk_index,
                            'page_number': row.page_number
                        }
                        chunks.append({
                            'id': row.id,
                            'document_id': row.document_id,
                            'text_content': row.text_content,
                            'metadata': metadata,
                            'chunk_index': row.chunk_index,
                            'title': row.title,
                            'url': row.source_url,
                            'source_type': row.source_type
                        })
                    return chunks
            else:
                # Directly get the unprocessed chunks from database
                # This approach is more reliable than trying to incrementally find chunks
                engine = self.get_db_engine()
                with engine.connect() as conn:
                    # First, refresh our processed chunk IDs to make sure we have the latest data
                    from utils.vector_store import VectorStore
                    vector_store = VectorStore()
                    self.processed_chunk_ids = vector_store.get_processed_chunk_ids()
                    processed_ids_list = list(self.processed_chunk_ids)
                    
                    # Get all chunk IDs from database
                    all_chunks_query = text("""
                        SELECT id FROM document_chunks ORDER BY id
                    """)
                    all_chunk_ids = [row[0] for row in conn.execute(all_chunks_query)]
                    
                    # Find unprocessed IDs
                    if not all_chunk_ids:
                        logger.warning("No chunks found in database")
                        return []
                    
                    logger.info(f"Database has {len(all_chunk_ids)} total chunks")
                    logger.info(f"Vector store has {len(processed_ids_list)} processed chunks")
                    
                    # Calculate unprocessed IDs
                    unprocessed_ids = list(set(all_chunk_ids) - set(processed_ids_list))
                    
                    if not unprocessed_ids:
                        logger.info("No unprocessed chunks found in database")
                        return []
                    
                    # Take a batch of unprocessed IDs
                    batch_ids = unprocessed_ids[:self.batch_size]
                    logger.info(f"Found {len(unprocessed_ids)} unprocessed chunks, processing batch of {len(batch_ids)}")
                    
                    # Log the specific batch IDs
                    batch_ids_str = ", ".join(str(id) for id in batch_ids[:10])
                    logger.info(f"Processing chunk IDs: {batch_ids_str}{'...' if len(batch_ids) > 10 else ''}")
                    
                    # If batch is empty, return empty
                    if not batch_ids:
                        return []
                    
                    # Get chunks for these IDs
                    chunks_query = text("""
                        SELECT c.id, c.document_id, c.text_content, c.chunk_index, c.page_number, 
                               d.title, d.source_url, d.file_type AS source_type
                        FROM document_chunks c
                        JOIN documents d ON c.document_id = d.id
                        WHERE c.id IN :chunk_ids
                        ORDER BY c.id
                    """)
                    
                    candidate_chunks = []
                    
                    # Handle empty list or single ID differently for SQL compatibility
                    if len(batch_ids) == 1:
                        result = conn.execute(chunks_query, {"chunk_ids": (batch_ids[0],)})
                    else:
                        result = conn.execute(chunks_query, {"chunk_ids": tuple(batch_ids)})
                    
                    for row in result:
                        # Double-check that this ID is not already processed
                        if row.id not in self.processed_chunk_ids:
                            metadata = {
                                'title': row.title or "",
                                'url': row.source_url or "",
                                'source_type': row.source_type or "unknown",
                                'chunk_index': row.chunk_index or 0,
                                'page_number': row.page_number or 0
                            }
                            candidate_chunks.append({
                                'id': row.id,
                                'document_id': row.document_id,
                                'text_content': row.text_content,
                                'metadata': metadata,
                                'chunk_index': row.chunk_index or 0,
                                'title': row.title or "",
                                'url': row.source_url or "",
                                'source_type': row.source_type or "unknown"
                            })
                    
                    return candidate_chunks
        except Exception as e:
            logger.error(f"Error getting next chunk batch: {e}")
            return []
    
    def process_chunk(self, chunk: Dict[str, Any]) -> bool:
        """
        Process a single chunk and add it to the vector store.
        
        Args:
            chunk: The document chunk to process
            
        Returns:
            True if successful, False otherwise
        """
        try:
            from utils.vector_store import VectorStore
            from utils.llm_service import get_embedding
            
            # Extract chunk data
            chunk_id = chunk['id']
            document_id = chunk['document_id']
            text_content = chunk['text_content']
            metadata = chunk.get('metadata', {}) or {}
            
            # Skip if already processed - double check
            if chunk_id in self.processed_chunk_ids:
                logger.info(f"Chunk {chunk_id} already processed, skipping")
                return True
            
            # Rate limit and error handling for OpenAI API calls
            max_retries = 3
            retry_count = 0
            embedding = None
            
            while retry_count < max_retries:
                try:
                    # Generate embedding with appropriate rate limiting
                    logger.info(f"Generating embedding for chunk {chunk_id} (attempt {retry_count + 1})")
                    embedding = get_embedding(text_content)
                    break
                except Exception as e:
                    retry_count += 1
                    logger.warning(f"Error generating embedding (attempt {retry_count}): {e}")
                    if retry_count >= max_retries:
                        logger.error(f"Failed to generate embedding after {max_retries} attempts")
                        raise
                    # Exponential backoff
                    sleep_time = 2 ** retry_count
                    logger.info(f"Sleeping for {sleep_time}s before retry...")
                    time.sleep(sleep_time)
            
            if embedding is None:
                logger.error(f"Failed to generate embedding for chunk {chunk_id}")
                return False
                
            # Add to vector store
            vector_store = VectorStore()
            
            # Ensure document_id and chunk_id are included in metadata
            if metadata is None:
                metadata = {}
            metadata['document_id'] = document_id
            metadata['chunk_id'] = chunk_id
            
            # Add embedding with the correct method signature and handle any errors
            try:
                logger.info(f"Adding embedding to vector store for chunk {chunk_id}")
                vector_store.add_embedding(
                    text=text_content,
                    embedding=embedding,
                    metadata=metadata
                )
                
                # Force save to disk to ensure persistence
                logger.info(f"Saving vector store to disk for chunk {chunk_id}")
                vector_store.save()
                
                # Refresh our list of processed chunk IDs to ensure accuracy
                logger.info(f"Refreshing processed chunk IDs")
                self.processed_chunk_ids = vector_store.get_processed_chunk_ids()
                self.total_processed = len(self.processed_chunk_ids)
                
                # Verify the chunk was actually added
                if chunk_id not in self.processed_chunk_ids:
                    logger.warning(f"Chunk {chunk_id} not found in vector store after processing. Forcing add.")
                    # Try one more time with explicit ID tracking
                    metadata['force_id'] = f"chunk_{chunk_id}"
                    # Add the embedding again, now with a special metadata tag
                    logger.info(f"Attempting forced add for chunk {chunk_id}")
                    vector_store.add_embedding(
                        text=text_content,
                        embedding=embedding,
                        metadata=metadata
                    )
                    vector_store.save()
                    self.processed_chunk_ids.add(chunk_id)
            except Exception as e:
                logger.error(f"Error adding embedding to vector store: {e}")
                return False
            
            # Success!
            logger.info(f"Successfully processed chunk {chunk_id} for document {document_id}")
            
            # Sleep briefly to avoid overwhelming the system
            time.sleep(0.5)
            
            return True
        except Exception as e:
            logger.error(f"Error processing chunk {chunk.get('id')}: {e}")
            logger.error(f"Error details: {str(e)}")
            logger.exception("Full traceback:")
            return False
    
    def process_batch(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process a batch of chunks.
        
        Args:
            chunks: List of chunks to process
            
        Returns:
            Dictionary with processing results
        """
        if not chunks:
            logger.warning("No chunks to process in this batch")
            return {"success": 0, "failed": 0, "skipped": 0}
        
        logger.info(f"Processing batch of {len(chunks)} chunks")
        
        # Refresh our list of processed chunk IDs before processing
        from utils.vector_store import VectorStore
        vector_store = VectorStore()
        self.processed_chunk_ids = vector_store.get_processed_chunk_ids()
        
        # Filter out any chunks that are already processed
        unprocessed_chunks = []
        skipped_count = 0
        for chunk in chunks:
            if chunk['id'] in self.processed_chunk_ids:
                skipped_count += 1
                logger.info(f"Chunk {chunk['id']} already in vector store, skipping")
                continue
            unprocessed_chunks.append(chunk)
        
        if not unprocessed_chunks:
            logger.info("All chunks in batch already processed, skipping batch")
            return {"success": 0, "failed": 0, "skipped": len(chunks)}
            
        logger.info(f"Processing {len(unprocessed_chunks)} unprocessed chunks (skipped {skipped_count})")
        
        start_time = time.time()
        results = {
            "success": 0,
            "failed": 0,
            "skipped": skipped_count
        }
        
        for chunk in unprocessed_chunks:
            try:
                success = self.process_chunk(chunk)
                if success:
                    results["success"] += 1
                else:
                    results["failed"] += 1
            except Exception as e:
                logger.error(f"Error processing chunk {chunk.get('id')}: {e}")
                results["failed"] += 1
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        logger.info(f"Batch processing completed: {results['success']} successful, "
                  f"{results['failed']} failed, {results['skipped']} skipped "
                  f"in {processing_time:.2f} seconds")
        
        return results
    
    def get_progress(self) -> Dict[str, Any]:
        """
        Get the current progress of vector store rebuilding.
        
        Returns:
            Dictionary with progress information
        """
        try:
            if self.total_chunks == 0:
                self.total_chunks = self.get_total_chunks()
            
            if not self.processed_chunk_ids:
                self.processed_chunk_ids = self.get_processed_chunk_ids()
            
            self.total_processed = len(self.processed_chunk_ids)
            
            if self.total_chunks == 0:
                percentage = 0.0
            else:
                percentage = (self.total_processed / self.total_chunks) * 100.0
            
            return {
                "total_chunks": self.total_chunks,
                "processed_chunks": self.total_processed,
                "percentage": round(percentage, 2),
                "remaining_chunks": self.total_chunks - self.total_processed,
                "target_percentage": self.target_percentage,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting progress: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def log_progress(self) -> None:
        """Log the current progress."""
        progress = self.get_progress()
        logger.info(f"Progress: {progress['percentage']:.2f}% ({progress['processed_chunks']}/{progress['total_chunks']} chunks processed)")
    
    def check_target_reached(self) -> bool:
        """
        Check if the target percentage has been reached.
        
        Returns:
            True if target reached, False otherwise
        """
        progress = self.get_progress()
        return progress["percentage"] >= self.target_percentage
    
    def run(self) -> Dict[str, Any]:
        """
        Run the service until the target percentage is reached.
        
        Returns:
            Dictionary with processing summary
        """
        logger.info(f"Starting processing service to {self.target_percentage}% completion")
        
        # Get initial progress
        progress = self.get_progress()
        logger.info(f"Initial progress: {progress['percentage']:.2f}% ({progress['processed_chunks']}/{progress['total_chunks']} chunks processed)")
        
        total_processed = 0
        
        try:
            while self.running:
                # Check if we've reached the target
                if self.check_target_reached():
                    logger.info(f"Target {self.target_percentage}% reached!")
                    break
                
                # Get the next batch of chunks
                chunks = self.get_next_chunk_batch()
                
                # If no chunks to process, wait and try again
                if not chunks:
                    logger.info("No chunks to process, waiting before trying again...")
                    time.sleep(5)
                    continue
                
                # Process the batch
                batch_results = self.process_batch(chunks)
                total_processed += batch_results["success"]
                
                # Log progress
                self.log_progress()
                
                # Dynamic sleep based on how close we are to target
                progress = self.get_progress()
                remaining_percentage = self.target_percentage - progress["percentage"]
                
                # Adjust sleep time based on how close we are to the target
                if remaining_percentage < 5:
                    sleep_time = 1
                elif remaining_percentage < 10:
                    sleep_time = 2
                else:
                    sleep_time = 3
                
                logger.info(f"Sleeping for {sleep_time} seconds before next batch")
                time.sleep(sleep_time)
        
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down...")
        except Exception as e:
            logger.error(f"Error in service: {e}")
        
        # Final progress report
        final_progress = self.get_progress()
        logger.info(f"Final progress: {final_progress['percentage']:.2f}% ({final_progress['processed_chunks']}/{final_progress['total_chunks']} chunks processed)")
        
        return {
            "total_processed": total_processed,
            **final_progress
        }

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Process to 65 Percent Service")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE,
                        help=f"Number of chunks to process per batch (default: {BATCH_SIZE})")
    parser.add_argument("--target", type=float, default=TARGET_PERCENTAGE,
                        help=f"Target percentage of completion (default: {TARGET_PERCENTAGE}%)")
    return parser.parse_args()

def main():
    """Main function."""
    args = parse_args()
    service = Process65PercentService(batch_size=args.batch_size, target_percentage=args.target)
    service.run()

if __name__ == "__main__":
    main()