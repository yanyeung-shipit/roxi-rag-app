#!/usr/bin/env python3
"""
Enhanced Batch Processor

This module provides an improved version of the BatchProcessor class
with more robust error handling, especially for database connection issues.
"""

import os
import sys
import time
import json
import logging
import datetime
import sqlalchemy.exc
from typing import Dict, Any, List, Set, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"logs/batch_processing/enhanced_batch_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Add the current directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import DocumentChunk
from utils.vector_store import VectorStore
from utils.llm_service import get_embedding

# Constants
CHECKPOINT_DIR = "logs/checkpoints"
DEFAULT_TARGET_PERCENTAGE = 50.0
DEFAULT_BATCH_SIZE = 5  # Smaller batches for stability
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
DB_MAX_RETRIES = 3
DB_RETRY_DELAY = 10  # seconds

# Ensure directories exist
os.makedirs(CHECKPOINT_DIR, exist_ok=True)
os.makedirs("logs/batch_processing", exist_ok=True)


class EnhancedBatchProcessor:
    """
    Enhanced version of the BatchProcessor class with better error handling.
    Processes document chunks in batches and adds them to the vector store.
    """

    def __init__(self, batch_size: int = DEFAULT_BATCH_SIZE, target_percentage: float = DEFAULT_TARGET_PERCENTAGE):
        """
        Initialize the batch processor.
        
        Args:
            batch_size: Number of chunks to process per batch
            target_percentage: Target percentage of completion to reach
        """
        self.batch_size = batch_size
        self.target_percentage = target_percentage
        self.vector_store = VectorStore()
        self.processed_chunk_ids = self._get_processed_chunk_ids()
        self.start_time = time.time()
        self.chunks_processed = 0
        self.db_error_count = 0
        
    def _get_processed_chunk_ids(self) -> Set[int]:
        """
        Get IDs of chunks that have already been processed.
        
        Returns:
            Set of chunk IDs that are already in the vector store
        """
        # Use the VectorStore's method directly to get processed chunk IDs
        processed_ids = self.vector_store.get_processed_chunk_ids()
        
        logger.info(f"Found {len(processed_ids)} processed chunk IDs in vector store")
        return processed_ids
    
    def _execute_db_query(self, query_func, *args, **kwargs):
        """
        Execute a database query with retry logic.
        
        Args:
            query_func: Function to execute
            
        Returns:
            Result of the query or None if failed
        """
        for attempt in range(DB_MAX_RETRIES):
            try:
                with app.app_context():
                    result = query_func(*args, **kwargs)
                    self.db_error_count = 0  # Reset error count on success
                    return result
            except sqlalchemy.exc.OperationalError as e:
                self.db_error_count += 1
                logger.error(f"Database operational error (attempt {attempt+1}/{DB_MAX_RETRIES}): {str(e)}")
                try:
                    db.session.rollback()
                    logger.info("Session rolled back")
                except Exception:
                    logger.error("Failed to rollback session")
                
                if attempt < DB_MAX_RETRIES - 1:
                    wait_time = DB_RETRY_DELAY * (attempt + 1)  # Exponential backoff
                    logger.info(f"Waiting {wait_time} seconds before database retry...")
                    time.sleep(wait_time)
            except sqlalchemy.exc.DatabaseError as e:
                self.db_error_count += 1
                logger.error(f"Database error (attempt {attempt+1}/{DB_MAX_RETRIES}): {str(e)}")
                try:
                    db.session.rollback()
                    logger.info("Session rolled back")
                except Exception:
                    logger.error("Failed to rollback session")
                
                if attempt < DB_MAX_RETRIES - 1:
                    wait_time = DB_RETRY_DELAY * (attempt + 1)
                    logger.info(f"Waiting {wait_time} seconds before database retry...")
                    time.sleep(wait_time)
            except Exception as e:
                self.db_error_count += 1
                logger.error(f"Unexpected error during database query (attempt {attempt+1}/{DB_MAX_RETRIES}): {str(e)}")
                try:
                    db.session.rollback()
                    logger.info("Session rolled back")
                except Exception:
                    logger.error("Failed to rollback session")
                
                if attempt < DB_MAX_RETRIES - 1:
                    wait_time = DB_RETRY_DELAY * (attempt + 1)
                    logger.info(f"Waiting {wait_time} seconds before database retry...")
                    time.sleep(wait_time)
        
        logger.error(f"Failed to execute database query after {DB_MAX_RETRIES} attempts")
        return None
    
    def get_progress(self) -> Dict[str, Any]:
        """
        Get the current progress of vector store rebuilding.
        
        Returns:
            Dictionary with progress information
        """
        def query_total_chunks():
            return db.session.query(DocumentChunk).count()
        
        # Execute with retry logic
        total_chunks = self._execute_db_query(query_total_chunks)
        
        if total_chunks is None:
            logger.warning("Could not get total chunk count, using cached data")
            # Use last known values or defaults
            processed_chunks = len(self.vector_store.documents)
            total_chunks = max(processed_chunks, 1261)  # Use known total or default
        else:
            processed_chunks = len(self.vector_store.documents)
        
        percentage = (processed_chunks / total_chunks) * 100 if total_chunks else 0
        
        # Calculate rate and ETA
        elapsed_time = max(1, time.time() - self.start_time)
        rate = self.chunks_processed / elapsed_time if elapsed_time > 0 else 0
        
        remaining_chunks = total_chunks - processed_chunks
        estimated_seconds_remaining = remaining_chunks / rate if rate > 0 else 0
        
        # Format time remaining
        hours, remainder = divmod(int(estimated_seconds_remaining), 3600)
        minutes, seconds = divmod(remainder, 60)
        time_remaining = f"{hours}h {minutes}m {seconds}s"
        
        return {
            "processed_chunks": processed_chunks,
            "total_chunks": total_chunks,
            "percentage": percentage,
            "rate_chunks_per_second": round(rate, 3),
            "elapsed_time": elapsed_time,
            "estimated_time_remaining": time_remaining
        }
    
    def get_next_chunk_batch(self) -> List[DocumentChunk]:
        """
        Get the next batch of chunks to process.
        
        Returns:
            List of DocumentChunk objects
        """
        def query_chunks():
            # Query for chunks that haven't been processed yet
            return (db.session.query(DocumentChunk)
                .filter(~DocumentChunk.id.in_(self.processed_chunk_ids))
                .order_by(DocumentChunk.id)
                .limit(self.batch_size)
                .all())
        
        # Execute with retry logic
        chunks = self._execute_db_query(query_chunks)
        
        if chunks is None:
            logger.error("Failed to retrieve next chunk batch")
            return []
            
        return chunks
    
    def save_checkpoint(self) -> None:
        """Save the current state of processed chunk IDs."""
        try:
            checkpoint_path = os.path.join(
                CHECKPOINT_DIR, 
                f"checkpoint_{datetime.datetime.now().isoformat()}.json"
            )
            
            progress = self.get_progress()
            
            data = {
                "timestamp": datetime.datetime.now().isoformat(),
                "processed_chunk_ids": list(self.processed_chunk_ids),
                "progress": progress
            }
            
            with open(checkpoint_path, 'w') as f:
                json.dump(data, f, indent=2)
                
            logger.info(f"Saved checkpoint with {len(self.processed_chunk_ids)} processed chunk IDs")
            
            # Keep only the 5 most recent checkpoints
            checkpoints = sorted([
                os.path.join(CHECKPOINT_DIR, f) 
                for f in os.listdir(CHECKPOINT_DIR) 
                if f.startswith("checkpoint_")
            ], key=os.path.getmtime, reverse=True)
            
            for old_checkpoint in checkpoints[5:]:
                os.remove(old_checkpoint)
                logger.debug(f"Removed old checkpoint: {old_checkpoint}")
                
        except Exception as e:
            logger.error(f"Error saving checkpoint: {str(e)}")
    
    def load_checkpoint(self) -> bool:
        """
        Load the previous checkpoint if it exists.
        
        Returns:
            True if checkpoint was loaded, False otherwise
        """
        try:
            checkpoints = sorted([
                os.path.join(CHECKPOINT_DIR, f) 
                for f in os.listdir(CHECKPOINT_DIR) 
                if f.startswith("checkpoint_")
            ], key=os.path.getmtime, reverse=True)
            
            if not checkpoints:
                logger.info("No checkpoint found")
                return False
                
            with open(checkpoints[0], 'r') as f:
                checkpoint_data = json.load(f)
                
            # Update processed chunk IDs
            self.processed_chunk_ids = set(checkpoint_data.get("processed_chunk_ids", []))
            
            logger.info(f"Loaded checkpoint from {checkpoint_data.get('timestamp', 'unknown')}")
            logger.info(f"Checkpoint contains {len(self.processed_chunk_ids)} processed chunk IDs")
            
            if "progress" in checkpoint_data:
                progress = checkpoint_data["progress"]
                logger.info(f"Checkpoint progress: {progress.get('percentage', 0)}% "
                           f"({progress.get('processed_chunks', 0)}/{progress.get('total_chunks', 0)} chunks)")
            
            return True
        except Exception as e:
            logger.error(f"Error loading checkpoint: {str(e)}")
            return False
    
    def process_chunk(self, chunk: DocumentChunk) -> bool:
        """
        Process a single chunk and add it to the vector store.
        
        Args:
            chunk: The DocumentChunk object to process
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # We'll create a safe version of the metadata outside the session context
            # to avoid any detached object issues
            chunk_id = chunk.id
            document_id = chunk.document_id
            chunk_index = chunk.chunk_index
            text_content = chunk.text_content
            
            # Safe document properties
            document_filename = ""
            document_title = ""
            formatted_citation = None
            document_doi = None
            
            # Extract document properties safely
            if hasattr(chunk, 'document') and chunk.document:
                document = chunk.document
                document_filename = document.filename or ""
                document_title = document.title or ""
                
                if hasattr(document, 'formatted_citation'):
                    formatted_citation = document.formatted_citation
                    
                if hasattr(document, 'doi'):
                    document_doi = document.doi
            
            # Create metadata
            metadata = {
                "chunk_id": chunk_id,
                "db_id": chunk_id,
                "document_id": document_id,
                "chunk_index": chunk_index,
                "filename": document_filename,
                "title": document_title
            }
            
            # Add citation information if available
            if formatted_citation:
                metadata["formatted_citation"] = formatted_citation
                
            if document_doi:
                metadata["doi"] = document_doi
            
            # Get text embedding
            embedding = get_embedding(text_content)
            
            if not embedding:
                logger.error(f"Failed to get embedding for chunk {chunk_id}")
                return False
            
            # Add to vector store
            self.vector_store.add_document(
                document_id=f"chunk_{chunk_id}",
                text=text_content,
                metadata=metadata,
                embedding=embedding
            )
            
            # Update processed IDs
            self.processed_chunk_ids.add(chunk_id)
            self.chunks_processed += 1
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing chunk {chunk.id}: {str(e)}")
            return False
    
    def process_batch(self, chunks: List[DocumentChunk]) -> Dict[str, Any]:
        """
        Process a batch of chunks.
        
        Args:
            chunks: List of DocumentChunk objects to process
            
        Returns:
            Dictionary with processing results
        """
        results = {
            "total": len(chunks),
            "successful": 0,
            "failed": 0,
            "chunk_ids_processed": [],
            "failed_chunk_ids": []
        }
        
        for chunk in chunks:
            logger.info(f"Processing chunk {chunk.id}")
            
            # Skip already processed chunks
            if chunk.id in self.processed_chunk_ids:
                logger.info(f"Chunk {chunk.id} already processed, skipping")
                continue
                
            # Attempt processing with retries
            success = False
            attempts = 0
            
            while not success and attempts < MAX_RETRIES:
                attempts += 1
                if attempts > 1:
                    logger.info(f"Retry {attempts}/{MAX_RETRIES} for chunk {chunk.id}")
                    time.sleep(RETRY_DELAY)
                
                success = self.process_chunk(chunk)
            
            if success:
                results["successful"] += 1
                results["chunk_ids_processed"].append(chunk.id)
                logger.info(f"Successfully processed chunk {chunk.id}")
            else:
                results["failed"] += 1
                results["failed_chunk_ids"].append(chunk.id)
                logger.error(f"Failed to process chunk {chunk.id} after {MAX_RETRIES} attempts")
        
        # Save checkpoint after each batch
        self.save_checkpoint()
        
        # Save vector store to disk after each batch
        try:
            self.vector_store.save_to_disk()
            logger.info("Saved vector store to disk")
        except Exception as e:
            logger.error(f"Error saving vector store to disk: {str(e)}")
        
        return results
    
    def run_until_target(self) -> Dict[str, Any]:
        """
        Process chunks in batches until the target percentage is reached.
        
        Returns:
            Dictionary with processing summary
        """
        summary = {
            "batches_processed": 0,
            "chunks_processed": 0,
            "chunks_failed": 0,
            "start_percentage": 0,
            "final_percentage": 0,
            "reached_target": False
        }
        
        # Load checkpoint
        self.load_checkpoint()
        
        # Get initial progress
        progress = self.get_progress()
        summary["start_percentage"] = progress["percentage"]
        
        logger.info(f"Starting batch processing to reach {self.target_percentage}% completion")
        logger.info(f"Initial progress: {progress['percentage']}% "
                   f"({progress['processed_chunks']}/{progress['total_chunks']} chunks)")
        
        # Process batches until target reached
        consecutive_db_errors = 0
        max_consecutive_db_errors = 3
        
        while progress["percentage"] < self.target_percentage:
            # If database errors persist, pause processing
            if self.db_error_count > 0:
                consecutive_db_errors += 1
                if consecutive_db_errors >= max_consecutive_db_errors:
                    logger.error(f"Too many consecutive database errors ({consecutive_db_errors}), pausing processing for recovery")
                    time.sleep(60)  # Wait for a minute
                    consecutive_db_errors = 0
            else:
                consecutive_db_errors = 0
            
            # Get next batch
            chunks = self.get_next_chunk_batch()
            
            if not chunks:
                logger.info("No more chunks to process")
                break
            
            # Process the batch
            logger.info(f"Processing batch of {len(chunks)} chunks")
            results = self.process_batch(chunks)
            
            # Update summary
            summary["batches_processed"] += 1
            summary["chunks_processed"] += results["successful"]
            summary["chunks_failed"] += results["failed"]
            
            # Update progress
            progress = self.get_progress()
            
            # Log progress
            logger.info(f"Batch {summary['batches_processed']} completed: "
                      f"{results['successful']}/{results['total']} chunks successful")
            logger.info(f"Progress: {progress['percentage']}% "
                      f"({progress['processed_chunks']}/{progress['total_chunks']} chunks)")
            logger.info(f"Processing rate: {progress['rate_chunks_per_second']} chunks/sec, "
                      f"Estimated time remaining: {progress['estimated_time_remaining']}")
            
            # Check if target reached
            if progress["percentage"] >= self.target_percentage:
                logger.info(f"Target percentage of {self.target_percentage}% reached!")
                summary["reached_target"] = True
                break
            
            # Short pause between batches to reduce resource usage
            time.sleep(1)
        
        # Final progress
        progress = self.get_progress()
        summary["final_percentage"] = progress["percentage"]
        
        logger.info(f"Batch processing completed")
        logger.info(f"Final progress: {progress['percentage']}% "
                   f"({progress['processed_chunks']}/{progress['total_chunks']} chunks)")
        logger.info(f"Estimated time remaining: {progress['estimated_time_remaining']}")
        logger.info(f"Processed {summary['chunks_processed']} chunks in {summary['batches_processed']} batches")
        
        return summary


def main():
    """Main function to run the batch processor."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Enhanced batch processing for vector store rebuilding")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Batch size")
    parser.add_argument("--target", type=float, default=DEFAULT_TARGET_PERCENTAGE, help="Target percentage")
    
    args = parser.parse_args()
    
    try:
        # Initialize processor
        processor = EnhancedBatchProcessor(
            batch_size=args.batch_size,
            target_percentage=args.target
        )
        
        # Run until target
        summary = processor.run_until_target()
        
        logger.info(f"Processing completed: {summary['final_percentage']}% reached")
        logger.info(f"Processed {summary['chunks_processed']} chunks in {summary['batches_processed']} batches")
        
        return 0
    except Exception as e:
        logger.error(f"Error in batch processing: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())