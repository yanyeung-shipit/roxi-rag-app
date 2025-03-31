#!/usr/bin/env python3
"""
Batch Rebuild to Target Percentage

This script processes chunks in batches until a target percentage of completion is reached.
It's designed to handle the correct document structure in the vector store.

Key features:
- Processes chunks in configurable batch sizes
- Checkpoints progress after each batch
- Robust error handling and retries
- Detailed logging and progress reporting
"""

import os
import sys
import time
import json
import logging
import datetime
import pickle
from typing import Dict, Any, List, Set, Optional
import traceback

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"logs/batch_processing/batch_rebuild_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
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
DEFAULT_TARGET_PERCENTAGE = 100.0
DEFAULT_BATCH_SIZE = 5
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

# Ensure checkpoint directory exists
os.makedirs(CHECKPOINT_DIR, exist_ok=True)
os.makedirs("logs/batch_processing", exist_ok=True)

class BatchProcessor:
    """
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
    
    def get_progress(self) -> Dict[str, Any]:
        """
        Get the current progress of vector store rebuilding.
        
        Returns:
            Dictionary with progress information
        """
        with app.app_context():
            # Get total chunks in database
            total_chunks = db.session.query(DocumentChunk).count()
            
            # Get vector store document count
            processed_chunks = len(self.vector_store.documents)
            
            # Calculate percentages
            percentage = round((processed_chunks / total_chunks) * 100, 1) if total_chunks > 0 else 0
            
            # Calculate rate and estimated time
            elapsed_time = time.time() - self.start_time
            rate = self.chunks_processed / elapsed_time if elapsed_time > 0 and self.chunks_processed > 0 else 0
            remaining_chunks = total_chunks - processed_chunks
            
            # Handle infinite or very large remaining time
            if rate > 0:
                est_time_remaining = remaining_chunks / rate
                if est_time_remaining > 1e9:  # Cap at a billion seconds (about 31 years)
                    est_time_remaining = 1e9
            else:
                est_time_remaining = 1e6  # Default to a large but finite number (about 11 days)
            
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
                "rate_chunks_per_second": round(rate, 2),
                "estimated_seconds_remaining": min(int(est_time_remaining), 1000000000),
                "estimated_time_remaining": time_str,
                "target_percentage": self.target_percentage
            }
    
    def get_next_chunk_batch(self) -> List[DocumentChunk]:
        """
        Get the next batch of chunks to process.
        
        Returns:
            List of DocumentChunk objects
        """
        with app.app_context():
            # Use join to eagerly load document relationship to avoid detached session issues
            chunks = db.session.query(DocumentChunk).options(
                db.joinedload(DocumentChunk.document)
            ).filter(
                ~DocumentChunk.id.in_(self.processed_chunk_ids) if self.processed_chunk_ids else True
            ).order_by(DocumentChunk.id).limit(self.batch_size).all()
            
            return chunks
    
    def save_checkpoint(self) -> None:
        """Save the current state of processed chunk IDs."""
        checkpoint_path = os.path.join(CHECKPOINT_DIR, "batch_rebuild_checkpoint.pkl")
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
        checkpoint_path = os.path.join(CHECKPOINT_DIR, "batch_rebuild_checkpoint.pkl")
        
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
            # We'll create a safe version of the metadata outside the session context
            # to avoid any detached object issues
            chunk_id = chunk.id
            document_id = chunk.document_id
            chunk_index = chunk.chunk_index
            text_content = chunk.text_content  # Using the correct attribute name from our model
            
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
            
            # Add to vector store - handle the needed structure
            self.vector_store.add_text(text_content, metadata=metadata)
            
            # Update processed IDs
            self.processed_chunk_ids.add(chunk_id)
            self.chunks_processed += 1
            
            return True
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
        while progress["percentage"] < self.target_percentage:
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
    # Parse command-line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Process chunks in batches until target percentage reached')
    parser.add_argument('--target', type=float, default=DEFAULT_TARGET_PERCENTAGE,
                        help=f'Target percentage to reach (default: {DEFAULT_TARGET_PERCENTAGE})')
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE,
                        help=f'Number of chunks to process per batch (default: {DEFAULT_BATCH_SIZE})')
    
    args = parser.parse_args()
    
    # Create and run batch processor
    processor = BatchProcessor(batch_size=args.batch_size, target_percentage=args.target)
    processor.run_until_target()


if __name__ == "__main__":
    main()