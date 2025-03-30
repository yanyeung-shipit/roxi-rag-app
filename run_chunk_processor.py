"""
Process Chunks Incrementally

This script processes chunks until a target percentage is reached.
It's designed to be robust in the Replit environment with proper 
error handling and progress tracking.
"""

import argparse
import json
import logging
import os
import sys
import time
import pickle
from typing import Dict, List, Set, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Import necessary modules
try:
    from models import Document, DocumentChunk
    from utils.vector_store import VectorStore
    from sqlalchemy import func
    from app import db
except ImportError as e:
    logger.error(f"Failed to import required modules: {e}")
    sys.exit(1)

# Constants
DEFAULT_BATCH_SIZE = 5
DEFAULT_TARGET_PERCENTAGE = 75.0
DEFAULT_DELAY = 3  # seconds between batches
CHECKPOINT_FILE = "processed_chunk_ids.checkpoint"
DOCUMENT_DATA_FILE = "document_data.pkl"  # Path to the vector store data


def get_processed_chunk_ids() -> Set[int]:
    """Get IDs of chunks that have already been processed from the vector store."""
    try:
        # We need to extract chunk IDs from the document metadata in the vector store
        processed_ids = set()
        
        # Load document data from the pickle file
        if os.path.exists(DOCUMENT_DATA_FILE):
            with open(DOCUMENT_DATA_FILE, 'rb') as f:
                loaded_data = pickle.load(f)
                documents = loaded_data.get('documents', {})
                
                # Extract chunk_id from metadata if it exists
                for doc_id, doc_data in documents.items():
                    metadata = doc_data.get('metadata', {})
                    if 'chunk_id' in metadata and metadata['chunk_id'] is not None:
                        try:
                            chunk_id = int(metadata['chunk_id'])
                            processed_ids.add(chunk_id)
                        except (ValueError, TypeError):
                            # Skip if chunk_id is not a valid integer
                            pass
            
            logger.info(f"Found {len(processed_ids)} processed chunk IDs in vector store")
        else:
            logger.warning(f"Vector store data file {DOCUMENT_DATA_FILE} not found")
        
        return processed_ids
    except Exception as e:
        logger.error(f"Error getting processed chunk IDs: {e}")
        return set()


def save_checkpoint(processed_ids: Set[int]) -> None:
    """Save the current state of processed chunk IDs."""
    try:
        with open(CHECKPOINT_FILE, 'w') as f:
            json.dump(list(processed_ids), f)
        logger.info(f"Saved checkpoint with {len(processed_ids)} processed chunks")
    except Exception as e:
        logger.error(f"Error saving checkpoint: {e}")


def load_checkpoint() -> Set[int]:
    """Load the previous checkpoint if it exists."""
    if not os.path.exists(CHECKPOINT_FILE):
        return set()
    
    try:
        with open(CHECKPOINT_FILE, 'r') as f:
            return set(json.load(f))
    except Exception as e:
        logger.error(f"Error loading checkpoint: {e}")
        return set()


def get_next_chunk_batch(batch_size: int, processed_ids: Set[int]) -> List[DocumentChunk]:
    """Get the next batch of chunks to process."""
    try:
        # Query chunks that haven't been processed yet
        session = db.session
        chunks = session.query(DocumentChunk).filter(
            ~DocumentChunk.id.in_(processed_ids)
        ).order_by(DocumentChunk.id).limit(batch_size).all()
        
        # We'll use the actual chunks from the database
        logger.info(f"Retrieved {len(chunks)} unprocessed chunks from database")
        
        return chunks
    except Exception as e:
        logger.error(f"Error getting next chunk batch: {e}")
        return []


def process_chunk(chunk: DocumentChunk) -> bool:
    """Process a single chunk and add it to the vector store."""
    try:
        # Get necessary data from the chunk
        chunk_text = chunk.text_content  # Use the correct field from the database schema
        metadata = {
            "document_id": chunk.document_id,
            "chunk_id": chunk.id,
            "page_number": chunk.page_number,
            "chunk_index": chunk.chunk_index,  # Use the correct field from the database schema
            "source_type": "document",
        }
        
        # Get document data
        session = db.session
        document = session.query(Document).filter_by(id=chunk.document_id).first()
        if document:
            metadata.update({
                "title": document.title,
                "url": document.source_url,  # Use the correct field from the database schema
                "file_type": document.file_type,
                "authors": document.authors,
                "doi": document.doi,
            })
            
            # Add publication year if available
            if document.publication_year:
                metadata["publication_year"] = document.publication_year
                
            # Add formatted citation if available
            if document.formatted_citation:
                metadata["formatted_citation"] = document.formatted_citation
        
        # Add to vector store using the add_text method
        vector_store = VectorStore()
        doc_id = vector_store.add_text(
            text=chunk_text,
            metadata=metadata
        )
        
        success = doc_id is not None
        
        if success:
            logger.info(f"Successfully processed chunk ID: {chunk.id} from document ID: {chunk.document_id}")
        else:
            logger.warning(f"Unsuccessful processing for chunk ID: {chunk.id}")
        
        return success
    except Exception as e:
        logger.error(f"Error processing chunk ID {chunk.id}: {e}")
        return False


def process_batch(chunks: List[DocumentChunk], processed_ids: Set[int]) -> Dict[str, Any]:
    """Process a batch of chunks."""
    results = {
        "processed": 0,
        "successful": 0,
        "failed": 0,
        "chunk_ids": []
    }
    
    if not chunks:
        logger.info("No chunks to process in this batch")
        return results
    
    for chunk in chunks:
        try:
            if chunk.id in processed_ids:
                logger.debug(f"Chunk ID {chunk.id} already processed, skipping")
                continue
                
            results["processed"] += 1
            success = process_chunk(chunk)
            
            if success:
                results["successful"] += 1
                results["chunk_ids"].append(chunk.id)
                processed_ids.add(chunk.id)
            else:
                results["failed"] += 1
        except Exception as e:
            logger.error(f"Error in batch processing for chunk ID {chunk.id}: {e}")
            results["failed"] += 1
    
    # Save checkpoint after each batch
    save_checkpoint(processed_ids)
    
    return results


def get_progress() -> Dict[str, Any]:
    """Get the current progress of vector store rebuilding."""
    try:
        # Get session
        session = db.session
        
        # Total chunks in database
        total_chunks = session.query(func.count(DocumentChunk.id)).scalar()
        # Total documents
        total_docs = session.query(func.count(Document.id)).scalar()
        
        # Get processed chunks count
        processed_ids = get_processed_chunk_ids()
        processed_chunks = len(processed_ids)
        
        # Calculate progress
        percentage = (processed_chunks / total_chunks * 100) if total_chunks > 0 else 0
        remaining_chunks = total_chunks - processed_chunks
        
        # Estimate time remaining (assuming 5 seconds per chunk as a rough estimate)
        est_seconds = remaining_chunks * 5
        est_minutes = est_seconds // 60
        est_hours = est_minutes // 60
        est_minutes %= 60
        
        result = {
            "vector_store_chunks": processed_chunks,
            "database_chunks": total_chunks,
            "total_documents": total_docs,
            "progress_percentage": percentage,
            "remaining_chunks": remaining_chunks,
            "estimated_minutes": est_minutes,
            "estimated_hours": est_hours
        }
        
        return result
    except Exception as e:
        logger.error(f"Error getting progress: {e}")
        return {}


def print_progress_info(progress: Dict[str, Any]) -> None:
    """Print progress information."""
    if not progress:
        logger.error("No progress information available")
        return
    
    logger.info("=" * 40)
    logger.info("VECTOR STORE REBUILD PROGRESS")
    logger.info("=" * 40)
    logger.info(f"Vector store:   {progress['vector_store_chunks']} chunks")
    logger.info(f"Database:       {progress['database_chunks']} chunks in {progress['total_documents']} documents")
    logger.info("-" * 40)
    
    percentage = progress['progress_percentage']
    logger.info(f"Progress:       {progress['vector_store_chunks']}/{progress['database_chunks']} chunks")
    logger.info(f"                {percentage:.1f}% complete")
    logger.info(f"Remaining:      {progress['remaining_chunks']} chunks")
    
    est_hours = progress['estimated_hours']
    est_mins = progress['estimated_minutes']
    logger.info(f"Est. time:      {est_hours}h {est_mins}m remaining")
    logger.info("=" * 40)


def process_chunks(batch_size: int = DEFAULT_BATCH_SIZE, 
                  target_percentage: float = DEFAULT_TARGET_PERCENTAGE, 
                  max_batches: Optional[int] = None,
                  delay_seconds: int = DEFAULT_DELAY) -> None:
    """
    Process chunks in batches until target percentage is reached or max_batches is hit.
    
    Args:
        batch_size: Number of chunks to process per batch
        target_percentage: Stop when this percentage is reached
        max_batches: Maximum number of batches to process (None for unlimited)
        delay_seconds: Delay between batches to avoid overloading
    """
    # Get initial progress
    progress = get_progress()
    if not progress:
        logger.error("Failed to get initial progress information")
        return
    
    print_progress_info(progress)
    
    # Load checkpoint if exists
    processed_ids = load_checkpoint()
    if processed_ids:
        logger.info(f"Loaded checkpoint with {len(processed_ids)} processed chunks")
    else:
        processed_ids = get_processed_chunk_ids()
        logger.info(f"No checkpoint found, using vector store data with {len(processed_ids)} chunks")
    
    # Process batches
    batch_count = 0
    current_percentage = progress['progress_percentage']
    
    while current_percentage < target_percentage and (max_batches is None or batch_count < max_batches):
        # Increment batch counter
        batch_count += 1
        logger.info(f"Processing batch {batch_count} (size: {batch_size})")
        
        # Get next batch
        chunks = get_next_chunk_batch(batch_size, processed_ids)
        if not chunks:
            logger.info("No more chunks to process")
            break
        
        # Process batch
        results = process_batch(chunks, processed_ids)
        logger.info(f"Batch {batch_count} results: {results['successful']} successful, {results['failed']} failed")
        
        # Get updated progress
        progress = get_progress()
        if progress:
            current_percentage = progress['progress_percentage']
            print_progress_info(progress)
        
        # Delay before next batch
        if current_percentage < target_percentage and (max_batches is None or batch_count < max_batches):
            logger.info(f"Waiting {delay_seconds} seconds before next batch...")
            time.sleep(delay_seconds)
    
    # Final status
    if current_percentage >= target_percentage:
        logger.info(f"Target reached! Final progress: {current_percentage:.1f}%")
    elif max_batches is not None and batch_count >= max_batches:
        logger.info(f"Maximum batches reached. Final progress: {current_percentage:.1f}%")
    else:
        logger.info(f"Processing complete. Final progress: {current_percentage:.1f}%")


def main():
    """Main function to run the script."""
    parser = argparse.ArgumentParser(description="Process chunks incrementally until target is reached")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                       help=f"Number of chunks to process per batch (default: {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--target", type=float, default=DEFAULT_TARGET_PERCENTAGE,
                       help=f"Target percentage to reach (default: {DEFAULT_TARGET_PERCENTAGE}%)")
    parser.add_argument("--max-batches", type=int, default=None,
                       help="Maximum number of batches to process (default: unlimited)")
    parser.add_argument("--delay", type=int, default=DEFAULT_DELAY,
                       help=f"Delay in seconds between batches (default: {DEFAULT_DELAY}s)")
    
    args = parser.parse_args()
    
    try:
        logger.info(f"Starting chunk processing to reach {args.target}% completion")
        logger.info(f"Using batch size of {args.batch_size} with {args.delay}s delay between batches")
        if args.max_batches:
            logger.info(f"Will process a maximum of {args.max_batches} batches")
        
        # Import app here to avoid circular imports
        from app import app
        
        # Use Flask application context
        with app.app_context():
            process_chunks(
                batch_size=args.batch_size,
                target_percentage=args.target,
                max_batches=args.max_batches,
                delay_seconds=args.delay
            )
    except KeyboardInterrupt:
        logger.info("Processing interrupted by user")
    except Exception as e:
        logger.error(f"Error processing chunks: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()