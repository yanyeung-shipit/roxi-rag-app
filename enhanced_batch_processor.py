#!/usr/bin/env python3
"""
Enhanced Batch Processor with Robust Database Connection Handling

This script processes chunks in batches with improved error handling
for PostgreSQL SSL connection issues and other database connection problems.
It implements exponential backoff and transaction management to ensure 
robust operation even in environments with intermittent connection issues.
"""

import os
import sys
import time
import logging
import json
import random
import pickle
import traceback
from typing import Dict, List, Set, Tuple, Any, Optional, Union
from datetime import datetime
from contextlib import contextmanager

import sqlalchemy.exc
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("enhanced_batch.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("EnhancedBatchProcessor")

# Constants
DEFAULT_BATCH_SIZE = 5
DEFAULT_TARGET_PERCENTAGE = 50.0  # Process up to 50% by default
MAX_RETRY_ATTEMPTS = 5
VECTOR_STORE_PATH = "document_data.pkl"
FAISS_INDEX_PATH = "faiss_index.bin"
CHECKPOINT_FILE = "enhanced_batch_checkpoint.json"

# Custom exceptions
class DatabaseConnectionError(Exception):
    """Exception raised for persistent database connection issues."""
    pass

class ProcessingError(Exception):
    """Exception raised for processing errors."""
    pass

class BatchProcessor:
    """
    Enhanced batch processor with robust database connection handling.
    
    This processor implements:
    1. Connection pooling with retries for database connection issues
    2. Checkpoint-based progress tracking to resume interrupted processing
    3. Transaction management to ensure database consistency
    4. Detailed logging and error handling
    """
    
    def __init__(self, batch_size: int = DEFAULT_BATCH_SIZE, 
                 target_percentage: float = DEFAULT_TARGET_PERCENTAGE):
        """
        Initialize the batch processor.
        
        Args:
            batch_size: Number of chunks to process per batch
            target_percentage: Target percentage of completion to reach
        """
        self.batch_size = batch_size
        self.target_percentage = target_percentage
        self.processed_chunk_ids = set()
        
        # Statistics tracking
        self.total_processed = 0
        self.total_errors = 0
        self.start_time = datetime.now()
        
        logger.info(f"Initializing enhanced batch processor with batch size {batch_size} "
                   f"and target percentage {target_percentage}%")
    
    def _get_processed_chunk_ids(self) -> Set[int]:
        """
        Get IDs of chunks that have already been processed from the vector store.
        
        Returns:
            Set of chunk IDs that are already in the vector store
        """
        if not os.path.exists(VECTOR_STORE_PATH):
            logger.warning(f"Vector store file {VECTOR_STORE_PATH} does not exist")
            return set()
            
        try:
            # Load the vector store
            with open(VECTOR_STORE_PATH, 'rb') as f:
                vector_store_data = pickle.load(f)
                
            # Get chunk IDs from vector store
            chunk_ids = set()
            if 'documents' in vector_store_data and vector_store_data['documents']:
                for doc_id, doc_data in vector_store_data['documents'].items():
                    if 'chunks' in doc_data:
                        for chunk_id in doc_data['chunks']:
                            chunk_ids.add(chunk_id)
            
            logger.info(f"Found {len(chunk_ids)} already processed chunks in vector store")
            return chunk_ids
            
        except Exception as e:
            logger.error(f"Error loading vector store: {str(e)}")
            return set()
    
    def _get_db_engine(self):
        """
        Get a SQLAlchemy database engine with proper connection settings.
        
        Returns:
            SQLAlchemy Engine with configured connection pool
        """
        from sqlalchemy import create_engine
        from sqlalchemy.pool import QueuePool

        # Get database URL from environment
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable not set")

        # Create custom connection arguments for PostgreSQL SSL issues
        connect_args = {
            "connect_timeout": 30,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5
        }
        
        # Create engine with connection pooling
        engine = create_engine(
            database_url,
            connect_args=connect_args,
            pool_size=5,
            max_overflow=10,
            pool_recycle=300,  # Recycle connections after 5 minutes
            pool_pre_ping=True,  # Test connections before using them
            poolclass=QueuePool
        )
        
        return engine
        
    @contextmanager
    def _db_session(self):
        """
        Context manager for database sessions with robust error handling.
        """
        from sqlalchemy.orm import sessionmaker

        # Create a new engine for this session
        engine = self._get_db_engine()
        Session = sessionmaker(bind=engine)
        session = Session()
        
        try:
            yield session
            session.commit()
        except sqlalchemy.exc.OperationalError as e:
            session.rollback()
            logger.error(f"Database operational error: {str(e)}")
            raise DatabaseConnectionError(f"Database connection error: {str(e)}")
        except sqlalchemy.exc.SQLAlchemyError as e:
            session.rollback()
            logger.error(f"SQLAlchemy error: {str(e)}")
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"Unexpected error in database session: {str(e)}")
            raise
        finally:
            session.close()
            engine.dispose()
    
    @retry(
        retry=retry_if_exception_type(DatabaseConnectionError),
        stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        before_sleep=lambda retry_state: logger.warning(
            f"Retry attempt {retry_state.attempt_number}/{MAX_RETRY_ATTEMPTS} "
            f"after database connection error. Waiting...")
    )
    def get_progress(self) -> Dict[str, Any]:
        """
        Get the current progress of vector store rebuilding.
        
        Returns:
            Dictionary with progress information
        """
        # Initialize with default values in case of error
        progress = {
            "total_chunks": 0,
            "processed_chunks": 0,
            "percentage_completed": 0,
            "target_percentage": self.target_percentage,
            "target_chunks": 0,
            "remaining_to_target": 0,
            "estimated_time_remaining": "Unknown"
        }
        
        try:
            # Load already processed chunks if not loaded
            if not self.processed_chunk_ids:
                self.processed_chunk_ids = self._get_processed_chunk_ids()
                
            # Get total chunks from database
            with self._db_session() as session:
                # Import here to avoid circular imports
                from sqlalchemy import func, text
                
                # Get total chunks count
                result = session.execute(text("SELECT COUNT(*) FROM document_chunks"))
                total_chunks = result.scalar() or 0
                
                # Calculate progress
                processed_chunks = len(self.processed_chunk_ids)
                percentage_completed = (processed_chunks / total_chunks * 100) if total_chunks > 0 else 0
                target_chunks = int(total_chunks * self.target_percentage / 100)
                remaining_to_target = max(0, target_chunks - processed_chunks)
                
                # Calculate estimated time
                elapsed_time = (datetime.now() - self.start_time).total_seconds()
                if processed_chunks > 0 and remaining_to_target > 0:
                    time_per_chunk = elapsed_time / processed_chunks
                    estimated_seconds = time_per_chunk * remaining_to_target
                    estimated_time = f"{estimated_seconds/60:.1f} minutes" if estimated_seconds < 3600 else f"{estimated_seconds/3600:.1f} hours"
                else:
                    estimated_time = "Unknown"
                
                progress = {
                    "total_chunks": total_chunks,
                    "processed_chunks": processed_chunks,
                    "percentage_completed": percentage_completed,
                    "target_percentage": self.target_percentage,
                    "target_chunks": target_chunks,
                    "remaining_to_target": remaining_to_target,
                    "estimated_time_remaining": estimated_time
                }
                
            logger.info(f"Progress: {progress['percentage_completed']:.2f}% "
                       f"({progress['processed_chunks']}/{progress['total_chunks']} chunks processed)")
            
            return progress
            
        except DatabaseConnectionError:
            # Let the retry decorator handle this
            raise
        except Exception as e:
            logger.error(f"Error checking progress: {str(e)}")
            return progress
    
    @retry(
        retry=retry_if_exception_type(DatabaseConnectionError),
        stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=4, max=60)
    )
    def get_next_chunk_batch(self) -> List:
        """
        Get the next batch of chunks to process.
        
        Returns:
            List of DocumentChunk objects
        """
        from sqlalchemy import text
        
        # Ensure we have the processed chunk IDs
        if not self.processed_chunk_ids:
            self.processed_chunk_ids = self._get_processed_chunk_ids()
        
        try:
            chunks = []
            with self._db_session() as session:
                # Construct query to exclude already processed chunks
                if self.processed_chunk_ids:
                    format_strings = ','.join(['%s' % id for id in self.processed_chunk_ids])
                    query = text(f"""
                        SELECT dc.id, dc.document_id, dc.chunk_index, dc.text_content, 
                               d.source_url, d.title, d.file_type, d.created_at
                        FROM document_chunks dc
                        JOIN documents d ON dc.document_id = d.id
                        WHERE dc.id NOT IN ({format_strings})
                        ORDER BY dc.document_id, dc.chunk_index
                        LIMIT :limit
                    """)
                else:
                    query = text("""
                        SELECT dc.id, dc.document_id, dc.chunk_index, dc.text_content, 
                               d.source_url, d.title, d.file_type, d.created_at
                        FROM document_chunks dc
                        JOIN documents d ON dc.document_id = d.id
                        ORDER BY dc.document_id, dc.chunk_index
                        LIMIT :limit
                    """)
                
                # Execute query with batch size
                result = session.execute(query, {"limit": self.batch_size})
                
                # Convert to list of dictionaries
                for row in result:
                    chunk = {
                        "id": row.id,
                        "document_id": row.document_id,
                        "chunk_index": row.chunk_index,
                        "text_content": row.text_content,  # Keep the original field name from DB
                        "embedding": None,  # We'll generate this when processing
                        "metadata": {
                            "url": row.source_url,
                            "title": row.title,
                            "source_type": row.file_type,
                            "upload_date": row.created_at
                        }
                    }
                    chunks.append(chunk)
                
            logger.info(f"Retrieved {len(chunks)} chunks for processing")
            return chunks
            
        except DatabaseConnectionError:
            # Let the retry decorator handle this
            raise
        except Exception as e:
            logger.error(f"Error getting next chunk batch: {str(e)}")
            traceback.print_exc()
            raise
    
    def save_checkpoint(self) -> None:
        """Save the current state of processed chunk IDs."""
        try:
            checkpoint_data = {
                "processed_chunk_ids": list(self.processed_chunk_ids),
                "total_processed": self.total_processed,
                "total_errors": self.total_errors,
                "timestamp": datetime.now().isoformat()
            }
            
            with open(CHECKPOINT_FILE, 'w') as f:
                json.dump(checkpoint_data, f)
                
            logger.info(f"Saved checkpoint with {len(self.processed_chunk_ids)} processed chunks")
            
        except Exception as e:
            logger.error(f"Error saving checkpoint: {str(e)}")
    
    def load_checkpoint(self) -> bool:
        """
        Load the previous checkpoint if it exists.
        
        Returns:
            True if checkpoint was loaded, False otherwise
        """
        if not os.path.exists(CHECKPOINT_FILE):
            logger.info("No checkpoint file found")
            return False
            
        try:
            with open(CHECKPOINT_FILE, 'r') as f:
                checkpoint_data = json.load(f)
                
            self.processed_chunk_ids = set(checkpoint_data.get("processed_chunk_ids", []))
            self.total_processed = checkpoint_data.get("total_processed", 0)
            self.total_errors = checkpoint_data.get("total_errors", 0)
            
            logger.info(f"Loaded checkpoint with {len(self.processed_chunk_ids)} processed chunks")
            return True
            
        except Exception as e:
            logger.error(f"Error loading checkpoint: {str(e)}")
            return False
    
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
            
            # Load vector store - it initializes and loads existing data automatically
            vector_store = VectorStore()
            
            # Process the chunk
            chunk_id = chunk["id"]
            document_id = chunk["document_id"]
            
            # Get text content from the chunk - it may be in "text" or "text_content" depending on the source
            text = chunk.get("text", chunk.get("text_content", ""))
            if not text:
                logger.error(f"No text content found in chunk {chunk_id}")
                return False
            
            # Generate embedding
            logger.info(f"Generating embedding for chunk {chunk_id}")
            embedding = get_embedding(text)
            
            # Add the embedding to vector store
            metadata = chunk["metadata"]
            metadata["chunk_index"] = chunk["chunk_index"]
            metadata["document_id"] = str(document_id)
            metadata["chunk_id"] = chunk_id
            
            # Use add_embedding to store the document with its metadata
            vector_store.add_embedding(
                text=text,
                embedding=embedding,
                metadata=metadata
            )
            
            # Save the vector store
            vector_store.save()
            
            # Update the processed chunk IDs
            self.processed_chunk_ids.add(chunk_id)
            
            logger.info(f"Successfully processed chunk {chunk_id} for document {document_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error processing chunk {chunk.get('id')}: {str(e)}")
            traceback.print_exc()
            return False
    
    def process_batch(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process a batch of chunks.
        
        Args:
            chunks: List of chunks to process
            
        Returns:
            Dictionary with processing results
        """
        start_time = time.time()
        batch_results = {
            "successful": 0,
            "failed": 0,
            "skipped": 0,
            "chunk_ids": [],
            "error_messages": []
        }
        
        if not chunks:
            logger.info("No chunks to process in this batch")
            return batch_results
        
        logger.info(f"Processing batch of {len(chunks)} chunks")
        
        # Process each chunk
        for chunk in chunks:
            chunk_id = chunk.get("id")
            
            # Skip already processed chunks
            if chunk_id in self.processed_chunk_ids:
                logger.debug(f"Skipping already processed chunk {chunk_id}")
                batch_results["skipped"] += 1
                continue
                
            # Process the chunk
            try:
                if self.process_chunk(chunk):
                    batch_results["successful"] += 1
                    batch_results["chunk_ids"].append(chunk_id)
                    self.total_processed += 1
                else:
                    batch_results["failed"] += 1
                    batch_results["error_messages"].append(f"Failed to process chunk {chunk_id}")
                    self.total_errors += 1
            except Exception as e:
                batch_results["failed"] += 1
                batch_results["error_messages"].append(f"Exception processing chunk {chunk_id}: {str(e)}")
                self.total_errors += 1
        
        # Calculate processing time
        elapsed_time = time.time() - start_time
        batch_results["elapsed_time"] = elapsed_time
        batch_results["chunks_per_second"] = len(chunks) / elapsed_time if elapsed_time > 0 else 0
        
        logger.info(f"Batch processing completed: {batch_results['successful']} successful, "
                   f"{batch_results['failed']} failed, {batch_results['skipped']} skipped "
                   f"in {elapsed_time:.2f} seconds")
        
        # Save checkpoint after each batch
        self.save_checkpoint()
        
        return batch_results
    
    def run_until_target(self) -> Dict[str, Any]:
        """
        Process chunks in batches until the target percentage is reached.
        
        Returns:
            Dictionary with processing summary
        """
        logger.info(f"Starting batch processing until {self.target_percentage}% completion")
        
        # Load checkpoint if available
        if not self.load_checkpoint():
            self.processed_chunk_ids = self._get_processed_chunk_ids()
        
        # Initial progress check
        progress = self.get_progress()
        
        # Main processing loop
        batches_processed = 0
        total_chunks_processed = 0
        
        try:
            while progress["percentage_completed"] < self.target_percentage:
                logger.info(f"Current progress: {progress['percentage_completed']:.2f}% "
                           f"(Target: {self.target_percentage}%)")
                
                # Get next batch of chunks
                chunks = self.get_next_chunk_batch()
                
                # If no more chunks to process, we're done
                if not chunks:
                    logger.info("No more chunks to process")
                    break
                
                # Process the batch
                batch_results = self.process_batch(chunks)
                
                # Increment counters
                batches_processed += 1
                total_chunks_processed += batch_results["successful"]
                
                # Update progress
                progress = self.get_progress()
                
                # Save a checkpoint
                self.save_checkpoint()
                
                # Add a small random sleep to avoid overwhelming the database
                sleep_time = random.uniform(0.5, 2.0)
                logger.info(f"Sleeping for {sleep_time:.2f} seconds before next batch")
                time.sleep(sleep_time)
        
        except KeyboardInterrupt:
            logger.info("Processing interrupted by user")
        except Exception as e:
            logger.error(f"Error during batch processing: {str(e)}")
            traceback.print_exc()
        
        # Final progress check
        final_progress = self.get_progress()
        
        # Generate summary
        end_time = datetime.now()
        elapsed_time = (end_time - self.start_time).total_seconds()
        
        summary = {
            "start_time": self.start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "elapsed_time_seconds": elapsed_time,
            "batches_processed": batches_processed,
            "total_chunks_processed": total_chunks_processed,
            "total_errors": self.total_errors,
            "initial_progress": progress,
            "final_progress": final_progress
        }
        
        logger.info("Batch processing complete")
        logger.info(f"Processed {total_chunks_processed} chunks in {batches_processed} batches")
        logger.info(f"Initial progress: {progress['percentage_completed']:.2f}%, "
                   f"Final progress: {final_progress['percentage_completed']:.2f}%")
        logger.info(f"Total elapsed time: {elapsed_time:.2f} seconds")
        
        return summary

def main():
    """Main function to run the batch processor."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Enhanced batch processor for vector store rebuilding")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, 
                        help=f"Batch size (default: {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--target", type=float, default=DEFAULT_TARGET_PERCENTAGE,
                        help=f"Target percentage (default: {DEFAULT_TARGET_PERCENTAGE}%)")
    
    args = parser.parse_args()
    
    # Create and run batch processor
    processor = BatchProcessor(batch_size=args.batch_size, target_percentage=args.target)
    
    try:
        summary = processor.run_until_target()
        
        # Print summary
        print("\n=== Processing Summary ===")
        print(f"Started: {summary['start_time']}")
        print(f"Ended: {summary['end_time']}")
        print(f"Elapsed time: {summary['elapsed_time_seconds']/60:.2f} minutes")
        print(f"Batches processed: {summary['batches_processed']}")
        print(f"Chunks processed: {summary['total_chunks_processed']}")
        print(f"Errors encountered: {summary['total_errors']}")
        print(f"Initial progress: {summary['initial_progress']['percentage_completed']:.2f}%")
        print(f"Final progress: {summary['final_progress']['percentage_completed']:.2f}%")
        
        # Save summary to file
        with open("enhanced_batch_summary.json", "w") as f:
            json.dump(summary, f, indent=2)
        
        return 0
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())