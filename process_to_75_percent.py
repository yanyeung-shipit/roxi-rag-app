#!/usr/bin/env python3
"""
Process chunks until reaching 75% completion.
This script continues the batch processing until 75% of chunks
are added to the vector store.
"""

import argparse
import logging
import sys
import time
import traceback
from typing import Dict, Any, List, Set, Optional

import models
from app import app, db
from models import DocumentChunk
from utils.vector_store import VectorStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Global constants
DEFAULT_BATCH_SIZE = 10
DEFAULT_TARGET_PERCENTAGE = 75.0
CHECKPOINT_FILE = "processed_chunk_ids.checkpoint"
PROGRESS_UPDATE_INTERVAL = 5  # batches

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
        self.processed_chunk_ids = set()
        self.total_chunks = 0
        self.start_time = time.time()
        self.already_processed = 0
        self.chunks_processed = 0
        
        # Load checkpoint if it exists
        self.load_checkpoint()
        
        # Get total number of chunks for progress reporting
        self.total_chunks = db.session.query(DocumentChunk).count()
        if self.total_chunks == 0:
            logging.warning("No chunks found in the database. Nothing to process.")
            sys.exit(0)
        
        # Get already processed chunks
        self.already_processed = self._get_processed_chunk_count()
        logging.info(f"Starting with {self.already_processed}/{self.total_chunks} chunks already processed")

    def _get_processed_chunk_ids(self) -> Set[int]:
        """
        Get IDs of chunks that have already been processed.
        
        Returns:
            Set of chunk IDs that are already in the vector store
        """
        # Extract chunk IDs from document metadata
        processed_ids = set()
        for doc_id, doc_data in self.vector_store.documents.items():
            if 'metadata' in doc_data and 'chunk_id' in doc_data['metadata']:
                try:
                    processed_ids.add(int(doc_data['metadata']['chunk_id']))
                except (ValueError, TypeError):
                    # Skip if chunk_id is not an integer or cannot be converted to one
                    logging.warning(f"Invalid chunk_id in metadata: {doc_data['metadata'].get('chunk_id')}")
                
        return processed_ids

    def _get_processed_chunk_count(self) -> int:
        """
        Get count of chunks that have already been processed.
        
        Returns:
            Number of chunks that are already in the vector store
        """
        return len(self._get_processed_chunk_ids())

    def get_progress(self) -> Dict[str, Any]:
        """
        Get the current progress of vector store rebuilding.
        
        Returns:
            Dictionary with progress information
        """
        current_processed = self._get_processed_chunk_count()
        percentage = (current_processed / self.total_chunks) * 100 if self.total_chunks > 0 else 0
        
        # Calculate rate and estimated time remaining
        elapsed_time = time.time() - self.start_time
        chunks_per_second = self.chunks_processed / elapsed_time if elapsed_time > 0 else 0
        
        # Estimate remaining time
        remaining_chunks = self.total_chunks - current_processed
        
        # Handle the case when chunks_per_second is very low or zero
        if chunks_per_second > 0.001:  # Prevent division by very small numbers
            remaining_seconds = remaining_chunks / chunks_per_second
            remaining_minutes = remaining_seconds / 60
            time_str = f"{int(remaining_minutes)}m {int(remaining_seconds % 60)}s"
        else:
            # If we can't calculate a reliable estimate
            remaining_seconds = float('inf')
            remaining_minutes = float('inf')
            time_str = "calculating..."
        
        return {
            "total_chunks": self.total_chunks,
            "processed_chunks": current_processed,
            "percentage": percentage,
            "remaining_chunks": remaining_chunks,
            "chunks_per_second": chunks_per_second,
            "estimated_remaining_minutes": remaining_minutes,
            "estimated_remaining_time": time_str
        }

    def get_next_chunk_batch(self) -> List[DocumentChunk]:
        """
        Get the next batch of chunks to process.
        
        Returns:
            List of DocumentChunk objects
        """
        # Get set of already processed chunk IDs
        processed_ids = self._get_processed_chunk_ids().union(self.processed_chunk_ids)
        
        # Query for chunks that haven't been processed yet
        query = db.session.query(DocumentChunk).filter(
            ~DocumentChunk.id.in_(processed_ids)
        ).order_by(DocumentChunk.id).limit(self.batch_size)
        
        return query.all()

    def save_checkpoint(self) -> None:
        """Save the current state of processed chunk IDs."""
        with open(CHECKPOINT_FILE, 'w') as f:
            f.write(','.join(map(str, self.processed_chunk_ids)))
        logging.info(f"Checkpoint saved with {len(self.processed_chunk_ids)} processed chunk IDs")

    def load_checkpoint(self) -> bool:
        """
        Load the previous checkpoint if it exists.
        
        Returns:
            True if checkpoint was loaded, False otherwise
        """
        try:
            with open(CHECKPOINT_FILE, 'r') as f:
                content = f.read().strip()
                if content:
                    self.processed_chunk_ids = set(map(int, content.split(',')))
                    logging.info(f"Loaded checkpoint with {len(self.processed_chunk_ids)} processed chunk IDs")
                    return True
        except FileNotFoundError:
            logging.info("No checkpoint file found, starting fresh")
        except Exception as e:
            logging.error(f"Error loading checkpoint: {e}")
        
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
            logging.info(f"Processing chunk {chunk.id}")
            
            # We'll create a safe version of the metadata outside the session context
            # to avoid any detached object issues
            chunk_id = chunk.id
            document_id = chunk.document_id
            chunk_index = chunk.chunk_index
            
            # Use content or text_content depending on what's available in the model
            text_content = chunk.content if hasattr(chunk, 'content') else chunk.text_content
            
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
            
            # Add citation if available
            if formatted_citation:
                metadata["citation"] = formatted_citation
                
            # Add DOI if available
            if document_doi:
                metadata["doi"] = document_doi
            
            # Add to vector store
            self.vector_store.add_text(text_content, metadata=metadata)
            
            # Mark as processed
            self.processed_chunk_ids.add(chunk_id)
            self.chunks_processed += 1
            
            logging.info(f"Successfully processed chunk {chunk_id}")
            return True
        except Exception as e:
            logging.error(f"Error processing chunk {chunk.id}: {e}")
            return False

    def process_batch(self, chunks: List[DocumentChunk]) -> Dict[str, Any]:
        """
        Process a batch of chunks.
        
        Args:
            chunks: List of DocumentChunk objects to process
            
        Returns:
            Dictionary with processing results
        """
        start_time = time.time()
        
        success_count = 0
        failed_ids = []
        
        for chunk in chunks:
            if self.process_chunk(chunk):
                success_count += 1
            else:
                failed_ids.append(chunk.id)
        
        # Save after each batch
        self.vector_store._save()
        self.save_checkpoint()
        
        elapsed = time.time() - start_time
        return {
            "batch_size": len(chunks),
            "success_count": success_count,
            "failed_ids": failed_ids,
            "elapsed_seconds": elapsed,
            "chunks_per_second": success_count / elapsed if elapsed > 0 else 0
        }

    def run_until_target(self) -> Dict[str, Any]:
        """
        Process chunks in batches until the target percentage is reached.
        
        Returns:
            Dictionary with processing summary
        """
        # Summary stats
        total_processed = 0
        batch_count = 0
        
        # Main processing loop
        while True:
            # Check if target percentage reached
            progress = self.get_progress()
            percentage = progress["percentage"]
            
            if percentage >= self.target_percentage:
                logging.info(f"Target percentage of {self.target_percentage}% reached!")
                break
            
            # Get next batch of chunks
            batch = self.get_next_chunk_batch()
            if not batch:
                logging.info("No more chunks to process")
                break
            
            # Process this batch
            batch_count += 1
            logging.info(f"Processing batch of {len(batch)} chunks")
            result = self.process_batch(batch)
            total_processed += result["success_count"]
            
            # Print progress every few batches
            if batch_count % PROGRESS_UPDATE_INTERVAL == 0 or not batch:
                progress = self.get_progress()
                logging.info(f"Batch {batch_count} completed: {result['success_count']}/{len(batch)} chunks successful")
                logging.info(f"Progress: {progress['percentage']:.1f}% ({progress['processed_chunks']}/{progress['total_chunks']} chunks)")
                logging.info(f"Processing rate: {result['chunks_per_second']:.2f} chunks/sec, Estimated time remaining: {progress['estimated_remaining_time']}")
        
        # Final progress report
        progress = self.get_progress()
        return {
            "batches_processed": batch_count,
            "chunks_processed": total_processed,
            "total_chunks": progress["total_chunks"],
            "processed_chunks": progress["processed_chunks"],
            "percentage": progress["percentage"],
            "remaining_chunks": progress["remaining_chunks"],
            "estimated_remaining_time": progress["estimated_remaining_time"]
        }

def main():
    """Main function to run the batch processor."""
    parser = argparse.ArgumentParser(description="Process chunks in batches until a target percentage is reached")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, 
                        help=f"Number of chunks to process per batch (default: {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--target-percentage", type=float, default=DEFAULT_TARGET_PERCENTAGE, 
                        help=f"Target percentage to reach (default: {DEFAULT_TARGET_PERCENTAGE}%)")
    
    args = parser.parse_args()
    
    # Create a Flask application context
    with app.app_context():
        # Run the batch processor
        processor = BatchProcessor(
            batch_size=args.batch_size,
            target_percentage=args.target_percentage
        )
        
        logging.info(f"Starting batch processing with target: {args.target_percentage}%")
        summary = processor.run_until_target()
        
        logging.info("===================================")
        logging.info("Batch processing completed")
        logging.info(f"Final progress: {summary['percentage']:.1f}% ({summary['processed_chunks']}/{summary['total_chunks']} chunks)")
        logging.info(f"Estimated time remaining: {summary['estimated_remaining_time']}")
        logging.info(f"Processed {summary['chunks_processed']} chunks in {summary['batches_processed']} batches")
        logging.info("===================================")

if __name__ == "__main__":
    main()