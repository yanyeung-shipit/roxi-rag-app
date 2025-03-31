#!/usr/bin/env python3
"""
Adaptive Document Processor

This processor automatically adapts to available system resources:
- Uses batch processing when resources are plentiful
- Falls back to single-chunk processing when resources are constrained
- Dynamically adjusts batch size based on system load
- Includes comprehensive monitoring and error handling

Usage:
    python processors/adaptive_processor.py [--target PERCENT] [--max-batch SIZE]
"""

import os
import sys
import time
import json
import psutil
import logging
import datetime
import argparse
import pickle
import traceback
import random
from typing import Dict, Any, List, Set, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"logs/adaptive_processor_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Add the current directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import relevant modules
try:
    from app import app, db
    from models import DocumentChunk
    from utils.vector_store import VectorStore
except ImportError as e:
    logger.error(f"Failed to import required modules: {e}")
    logger.error("Please ensure you're running this script from the project root directory")
    sys.exit(1)

# Constants
CHECKPOINT_DIR = "logs/checkpoints"
DEFAULT_TARGET_PERCENTAGE = 100.0  # Default target completion percentage
MAX_BATCH_SIZE = 10  # Maximum batch size for optimal conditions
MIN_BATCH_SIZE = 1  # Minimum batch size (single-chunk processing)
MAX_RETRIES = 3     # Maximum number of retries for failed chunks
RETRY_DELAY = 5     # Seconds to wait between retries

# Resource thresholds
HIGH_CPU_THRESHOLD = 75.0  # Percent
HIGH_MEMORY_THRESHOLD = 80.0  # Percent

# Ensure required directories exist
os.makedirs(CHECKPOINT_DIR, exist_ok=True)
os.makedirs("logs/batch_processing", exist_ok=True)


class ResourceMonitor:
    """Monitors system resources and determines optimal processing parameters."""
    
    @staticmethod
    def get_system_resources() -> Dict[str, float]:
        """
        Get current system resource usage.
        
        Returns:
            Dict with CPU and memory usage percentages
        """
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory_percent = psutil.virtual_memory().percent
            
            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent
            }
        except Exception as e:
            logger.warning(f"Error getting system resources: {e}")
            # Return conservative estimates if monitoring fails
            return {
                "cpu_percent": 70.0,
                "memory_percent": 70.0
            }
    
    @staticmethod
    def determine_batch_size(resources: Dict[str, float], max_batch_size: int = MAX_BATCH_SIZE) -> int:
        """
        Determine optimal batch size based on current resource usage.
        
        Args:
            resources: Dict with CPU and memory usage percentages
            max_batch_size: Maximum allowed batch size
            
        Returns:
            Optimal batch size (1 to max_batch_size)
        """
        cpu_percent = resources["cpu_percent"]
        memory_percent = resources["memory_percent"]
        
        # Conservative approach - if either resource is high, reduce batch size
        if cpu_percent > HIGH_CPU_THRESHOLD or memory_percent > HIGH_MEMORY_THRESHOLD:
            # Resources are constrained, use single-chunk processing
            logger.info(f"Resources constrained (CPU: {cpu_percent}%, Memory: {memory_percent}%), using single-chunk processing")
            return MIN_BATCH_SIZE
        
        # Calculate a dynamic batch size based on available resources
        # The formula gives higher batch sizes when resources are plentiful
        # and lower batch sizes when resources are more constrained
        cpu_factor = 1 - (cpu_percent / 100)
        memory_factor = 1 - (memory_percent / 100)
        
        # Use the more constrained resource as the limiting factor
        limiting_factor = min(cpu_factor, memory_factor)
        
        # Calculate batch size (1 to max_batch_size)
        batch_size = max(MIN_BATCH_SIZE, min(max_batch_size, int(limiting_factor * max_batch_size) + 1))
        
        logger.info(f"Current resources - CPU: {cpu_percent}%, Memory: {memory_percent}%, Batch size: {batch_size}")
        return batch_size


class AdaptiveProcessor:
    """
    Processes document chunks with adaptive batch sizing based on system resources.
    """
    
    def __init__(self, target_percentage: float = DEFAULT_TARGET_PERCENTAGE, max_batch_size: int = MAX_BATCH_SIZE):
        """
        Initialize the adaptive processor.
        
        Args:
            target_percentage: Target percentage of completion to reach
            max_batch_size: Maximum batch size to use when resources are plentiful
        """
        self.target_percentage = target_percentage
        self.max_batch_size = max_batch_size
        self.vector_store = VectorStore()
        self.processed_chunk_ids = self._get_processed_chunk_ids()
        self.resource_monitor = ResourceMonitor()
        self.start_time = time.time()
        self.chunks_processed = 0
        self.total_batches = 0
        
    def _get_processed_chunk_ids(self) -> Set[int]:
        """
        Get IDs of chunks that have already been processed.
        
        Returns:
            Set of chunk IDs that are already in the vector store
        """
        processed_ids = self.vector_store.get_processed_chunk_ids()
        logger.info(f"Found {len(processed_ids)} processed chunk IDs in vector store")
        return processed_ids
    
    def get_progress(self) -> Dict[str, Any]:
        """
        Get the current progress of vector store rebuilding.
        
        Returns:
            Dictionary with progress information
        """
        # Retry up to 3 times for database operations
        max_retries = 3
        retry_delay = 5
        total_chunks = 0
        
        for attempt in range(max_retries):
            try:
                with app.app_context():
                    # Get total chunks in database
                    total_chunks = db.session.query(DocumentChunk).count()
                    break  # Success, exit retry loop
            except Exception as e:
                logger.error(f"Database error on attempt {attempt+1}/{max_retries}: {str(e)}")
                if "SSL connection has been closed unexpectedly" in str(e):
                    logger.warning("SSL connection error detected, attempting to rollback and reconnect")
                    try:
                        with app.app_context():
                            db.session.rollback()
                    except Exception as rollback_error:
                        logger.error(f"Error during rollback: {str(rollback_error)}")
                
                if attempt < max_retries - 1:
                    sleep_time = retry_delay * (attempt + 1)
                    logger.info(f"Retrying in {sleep_time} seconds...")
                    time.sleep(sleep_time)
                else:
                    logger.error("Maximum retries reached, using cached or default values")
                    # If we can't get fresh data, use the last known value or a default
                    if hasattr(self, '_last_total_chunks') and self._last_total_chunks > 0:
                        total_chunks = self._last_total_chunks
                        logger.info(f"Using cached value of {total_chunks} total chunks")
                    else:
                        total_chunks = 1000  # Fallback default
                        logger.warning(f"Using default value of {total_chunks} total chunks")
        
        # Cache the value for potential future failures
        self._last_total_chunks = total_chunks
            
        # Get vector store document count
        processed_chunks = len(self.processed_chunk_ids)
        
        # Calculate percentages
        percentage = round((processed_chunks / total_chunks) * 100, 1) if total_chunks > 0 else 0
        
        # Calculate rate and estimated time
        elapsed_time = time.time() - self.start_time
        rate = self.chunks_processed / elapsed_time if elapsed_time > 0 and self.chunks_processed > 0 else 0
        remaining_chunks = total_chunks - processed_chunks
        
        # Handle infinite or very large remaining time
        if rate > 0:
            est_time_remaining = remaining_chunks / rate
            if est_time_remaining > 1e9:  # Cap at a billion seconds
                est_time_remaining = 1e9
        else:
            est_time_remaining = 1e6  # Default to a large but finite number
        
        # Format estimated time for display
        minutes, seconds = divmod(int(est_time_remaining), 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        
        # Create time string
        if days > 0:
            time_str = f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            time_str = f"{hours}h {minutes}m"
        else:
            time_str = f"{minutes}m {seconds}s"
        
        return {
            "total_chunks": total_chunks,
            "processed_chunks": processed_chunks,
            "percentage": percentage,
            "remaining_chunks": remaining_chunks,
            "chunks_processed_this_session": self.chunks_processed,
            "total_batches": self.total_batches,
            "rate_chunks_per_second": round(rate, 2),
            "estimated_seconds_remaining": min(int(est_time_remaining), 1000000000),
            "estimated_time_remaining": time_str,
            "target_percentage": self.target_percentage
        }
    
    def get_next_chunk_batch(self, batch_size: int) -> List[DocumentChunk]:
        """
        Get the next batch of chunks to process.
        
        Args:
            batch_size: Number of chunks to retrieve
            
        Returns:
            List of DocumentChunk objects
        """
        # Retry up to 3 times for database operations
        max_retries = 3
        retry_delay = 5
        chunks = []
        
        for attempt in range(max_retries):
            try:
                with app.app_context():
                    # Use join to eagerly load document relationship to avoid detached session issues
                    chunks = db.session.query(DocumentChunk).options(
                        db.joinedload(DocumentChunk.document)
                    ).filter(
                        ~DocumentChunk.id.in_(self.processed_chunk_ids) if self.processed_chunk_ids else True
                    ).order_by(DocumentChunk.id).limit(batch_size).all()
                    
                    # Make a copy of all needed data to avoid detached session issues
                    if chunks:
                        # Log successful retrieval
                        logger.info(f"Successfully retrieved {len(chunks)} chunks on attempt {attempt+1}")
                    break  # Success, exit retry loop
            except Exception as e:
                logger.error(f"Database error on get_next_chunk_batch attempt {attempt+1}/{max_retries}: {str(e)}")
                if "SSL connection has been closed unexpectedly" in str(e):
                    logger.warning("SSL connection error detected, attempting to rollback and reconnect")
                    try:
                        with app.app_context():
                            db.session.rollback()
                    except Exception as rollback_error:
                        logger.error(f"Error during rollback: {str(rollback_error)}")
                
                if attempt < max_retries - 1:
                    sleep_time = retry_delay * (attempt + 1)
                    logger.info(f"Retrying get_next_chunk_batch in {sleep_time} seconds...")
                    time.sleep(sleep_time)
                else:
                    logger.error("Maximum retries reached, returning empty chunk list")
                    return []
        
        return chunks
    
    def save_checkpoint(self) -> None:
        """Save the current state of processed chunk IDs."""
        checkpoint_path = os.path.join(CHECKPOINT_DIR, "adaptive_processor_checkpoint.pkl")
        checkpoint_data = {
            "processed_chunk_ids": self.processed_chunk_ids,
            "timestamp": datetime.datetime.now().isoformat(),
            "progress": self.get_progress()
        }
        
        try:
            with open(checkpoint_path, 'wb') as f:
                pickle.dump(checkpoint_data, f)
            logger.info(f"Checkpoint saved with {len(self.processed_chunk_ids)} processed chunk IDs")
        except Exception as e:
            logger.error(f"Error saving checkpoint: {str(e)}")
    
    def load_checkpoint(self) -> bool:
        """
        Load the previous checkpoint if it exists.
        
        Returns:
            True if checkpoint was loaded, False otherwise
        """
        checkpoint_path = os.path.join(CHECKPOINT_DIR, "adaptive_processor_checkpoint.pkl")
        
        if not os.path.exists(checkpoint_path):
            logger.info("No checkpoint found, starting fresh")
            return False
        
        try:
            with open(checkpoint_path, 'rb') as f:
                checkpoint_data = pickle.load(f)
            
            # Update processed chunk IDs
            self.processed_chunk_ids.update(checkpoint_data.get("processed_chunk_ids", set()))
            
            # Log checkpoint info
            logger.info(f"Loaded checkpoint from {checkpoint_data.get('timestamp', 'unknown time')}")
            logger.info(f"Checkpoint contains {len(self.processed_chunk_ids)} processed chunk IDs")
            
            # Log progress from checkpoint
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
            # Create a safe version of the metadata outside the session context
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
                "db_id": chunk_id,  # Include both for compatibility
                "document_id": document_id,
                "source_type": "pdf",  # Default value
                "chunk_index": chunk_index,
                "filename": document_filename,
                "title": document_title
            }
            
            # Add citation information if available
            if formatted_citation:
                metadata["citation"] = formatted_citation
            if document_doi:
                metadata["doi"] = document_doi
            
            # Add to vector store with exponential backoff for rate limits
            max_retries = 5
            base_delay = 2  # Base delay in seconds
            
            for attempt in range(max_retries):
                try:
                    # Add text to vector store
                    self.vector_store.add_text(text_content, metadata=metadata)
                    
                    # Update processed IDs
                    self.processed_chunk_ids.add(chunk_id)
                    self.chunks_processed += 1
                    
                    return True
                except Exception as inner_e:
                    error_str = str(inner_e).lower()
                    
                    # Check for rate limit errors (specific to OpenAI's error messages)
                    if "rate limit" in error_str or "too many requests" in error_str:
                        # Calculate exponential backoff with jitter
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                        delay = min(delay, 60)  # Cap at 60 seconds
                        
                        logger.warning(f"Rate limit error detected. Retrying in {delay:.1f} seconds... "
                                     f"(Attempt {attempt+1}/{max_retries})")
                        time.sleep(delay)
                    else:
                        # For non-rate-limit errors, don't retry
                        raise
            
            # If we got here, we've exhausted our retries
            logger.error(f"Failed to process chunk {chunk_id} after {max_retries} attempts due to rate limits")
            return False
        except Exception as e:
            logger.error(f"Error processing chunk {chunk.id}: {str(e)}")
            logger.error(traceback.format_exc())
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
            
            # Try with retries
            success = False
            attempts = 0
            
            while not success and attempts < MAX_RETRIES:
                attempts += 1
                if attempts > 1:
                    logger.info(f"Retry {attempts}/{MAX_RETRIES} for chunk {chunk.id}")
                    time.sleep(RETRY_DELAY)  # Wait before retry
                
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
        self.total_batches += 1
        
        return results
    
    def run_until_target(self) -> Dict[str, Any]:
        """
        Process chunks adaptively until the target percentage is reached.
        
        Returns:
            Dictionary with processing summary
        """
        summary = {
            "batches_processed": 0,
            "chunks_processed": 0,
            "chunks_failed": 0,
            "start_percentage": 0,
            "final_percentage": 0,
            "reached_target": False,
            "resource_limited_count": 0
        }
        
        # Load checkpoint
        self.load_checkpoint()
        
        # Get initial progress
        progress = self.get_progress()
        summary["start_percentage"] = progress["percentage"]
        
        logger.info(f"Starting adaptive processing to reach {self.target_percentage}% completion")
        logger.info(f"Initial progress: {progress['percentage']}% "
                   f"({progress['processed_chunks']}/{progress['total_chunks']} chunks)")
        
        # Process batches until target reached
        while progress["percentage"] < self.target_percentage:
            # Check system resources and determine batch size
            resources = self.resource_monitor.get_system_resources()
            batch_size = self.resource_monitor.determine_batch_size(resources, self.max_batch_size)
            
            # Track if we're resource limited
            if batch_size == MIN_BATCH_SIZE:
                summary["resource_limited_count"] += 1
            
            # Get next batch
            chunks = self.get_next_chunk_batch(batch_size)
            
            if not chunks:
                logger.info("No more chunks to process")
                break
            
            # Process the batch
            mode = "single-chunk" if batch_size == 1 else f"batch ({batch_size} chunks)"
            logger.info(f"Processing in {mode} mode")
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
            
            # Add a delay to avoid overwhelming the system and allow resources to recover
            # Use a longer delay for single-chunk mode (resource constrained)
            if batch_size == MIN_BATCH_SIZE:
                logger.info("Resource constrained mode, using longer delay between chunks")
                time.sleep(5)  # 5 seconds in resource-constrained mode
            else:
                time.sleep(3)  # 3 seconds in normal mode
        
        # Final progress
        progress = self.get_progress()
        summary["final_percentage"] = progress["percentage"]
        
        # Calculate resource limitation percentage
        total_iterations = summary["batches_processed"]
        if total_iterations > 0:
            resource_limited_percent = (summary["resource_limited_count"] / total_iterations) * 100
        else:
            resource_limited_percent = 0
        
        logger.info(f"Adaptive processing completed")
        logger.info(f"Final progress: {progress['percentage']}% "
                   f"({progress['processed_chunks']}/{progress['total_chunks']} chunks)")
        logger.info(f"Estimated time remaining: {progress['estimated_time_remaining']}")
        logger.info(f"Processed {summary['chunks_processed']} chunks in {summary['batches_processed']} batches")
        logger.info(f"Resource limited: {resource_limited_percent:.1f}% of the time")
        
        return summary


def main():
    """Main function to run the adaptive processor."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Adaptively process chunks based on system resources')
    parser.add_argument('--target', type=float, default=DEFAULT_TARGET_PERCENTAGE,
                        help=f'Target percentage to reach (default: {DEFAULT_TARGET_PERCENTAGE})')
    parser.add_argument('--max-batch', type=int, default=MAX_BATCH_SIZE,
                        help=f'Maximum batch size when resources are plentiful (default: {MAX_BATCH_SIZE})')
    
    args = parser.parse_args()
    
    # Print startup banner
    print("\n" + "="*80)
    print(" ROXI ADAPTIVE DOCUMENT PROCESSOR ".center(80, "="))
    print("="*80 + "\n")
    print(f"Target completion: {args.target}%")
    print(f"Maximum batch size: {args.max_batch}")
    print(f"Processor will automatically adjust to available system resources")
    print(f"Processing will continue until target is reached")
    print(f"Progress is automatically saved to checkpoints\n")
    
    # Create and run adaptive processor
    processor = AdaptiveProcessor(target_percentage=args.target, max_batch_size=args.max_batch)
    processor.run_until_target()


if __name__ == "__main__":
    main()