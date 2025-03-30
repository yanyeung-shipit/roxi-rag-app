"""
Background Chunk Processing Script

This script continually processes chunks until a target percentage is reached.
It runs in the background and logs progress to a dedicated file.

Usage:
    python process_chunks_background.py [--target PERCENTAGE] [--batch-size SIZE] [--delay SECONDS]
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Set, Tuple, Any, Union

from sqlalchemy import func
from sqlalchemy.orm import sessionmaker

import models
from app import db
from utils.vector_store import VectorStore

# Configure logging
log_file = 'process_chunks_background.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Constants
DEFAULT_BATCH_SIZE = 5
DEFAULT_DELAY_SECONDS = 3
DEFAULT_TARGET_PERCENTAGE = 75.0

# Initialize Vector Store
vector_store = VectorStore()

def get_processed_chunk_ids() -> Set[int]:
    """Get the IDs of chunks that have already been processed."""
    return vector_store.get_processed_chunk_ids()

def get_progress() -> Dict[str, Any]:
    """Get current progress information."""
    # Get total chunks from database using the correct table names from models.py
    with db.session() as session:
        # DocumentChunk maps to the 'document_chunks' table
        total_chunks = session.query(func.count(models.DocumentChunk.id)).scalar()
        # Document maps to the 'documents' table
        total_documents = session.query(func.count(models.Document.id)).scalar()
    
    # Get processed chunks from vector store
    processed_chunk_ids = get_processed_chunk_ids()
    processed_count = len(processed_chunk_ids)
    
    # Calculate progress percentage
    progress_percentage = (processed_count / total_chunks * 100) if total_chunks > 0 else 0
    
    # Calculate remaining chunks
    remaining_chunks = total_chunks - processed_count
    
    # Calculate estimated time
    avg_time_per_batch = 3  # seconds, estimated
    batches_remaining = remaining_chunks / DEFAULT_BATCH_SIZE
    est_seconds_remaining = batches_remaining * (avg_time_per_batch + DEFAULT_DELAY_SECONDS)
    est_hours = int(est_seconds_remaining // 3600)
    est_minutes = int((est_seconds_remaining % 3600) // 60)
    
    return {
        'processed_count': processed_count,
        'total_chunks': total_chunks,
        'total_documents': total_documents,
        'progress_percentage': progress_percentage,
        'remaining_chunks': remaining_chunks,
        'est_hours': est_hours,
        'est_minutes': est_minutes,
        'processed_chunk_ids': processed_chunk_ids
    }

def get_next_chunk_batch(batch_size: int, processed_chunk_ids: Set[int]) -> List[models.DocumentChunk]:
    """Get the next batch of unprocessed chunks."""
    with db.session() as session:
        # Make sure to use the correct table name from the models.py
        # The table name is 'document_chunks' as defined in the DocumentChunk model
        chunks = session.query(models.DocumentChunk).filter(
            ~models.DocumentChunk.id.in_(processed_chunk_ids)
        ).limit(batch_size).all()
        
        # Detach the chunks from the session
        session.expunge_all()
        
    return chunks

def process_chunk(chunk: models.DocumentChunk) -> bool:
    """Process a single chunk and add it to the vector store."""
    try:
        # Get the document metadata
        with db.session() as session:
            document = session.query(models.Document).filter_by(id=chunk.document_id).first()
            if not document:
                logger.error(f"Document not found for chunk ID {chunk.id} (document_id: {chunk.document_id})")
                return False
                
            # Using the correct field names from models.py
            metadata = {
                'document_id': document.id,
                'chunk_id': chunk.id,
                'document_type': document.file_type,  # Changed from document_type to file_type
                'title': document.title,
                'url': document.source_url,  # Changed from url to source_url
                'source': document.file_path,  # Using file_path as source
                'authors': document.authors,
                'doi': document.doi,
                'chunk_index': chunk.chunk_index,
                'total_chunks': len(document.chunks) if document.chunks else 0,  # Calculate total chunks from relationship
            }
        
        # Add the chunk to the vector store
        vector_store.add_text(chunk.text_content, metadata)  # Changed from content to text_content
        logger.info(f"Successfully processed chunk ID {chunk.id}")
        return True
    except Exception as e:
        logger.error(f"Error processing chunk ID {chunk.id}: {str(e)}")
        return False

def process_batch(chunks: List[models.DocumentChunk]) -> Dict[str, Any]:
    """Process a batch of chunks."""
    results = {
        'success_count': 0,
        'error_count': 0,
        'processed_ids': []
    }
    
    for chunk in chunks:
        success = process_chunk(chunk)
        if success:
            results['success_count'] += 1
            results['processed_ids'].append(chunk.id)
        else:
            results['error_count'] += 1
    
    # Save the vector store after each batch
    vector_store.save()
    logger.info(f"Vector store saved successfully after processing {len(chunks)} chunks")
    
    return results

def process_chunks_background(batch_size: int = DEFAULT_BATCH_SIZE, 
                   target_percentage: float = DEFAULT_TARGET_PERCENTAGE,
                   delay_seconds: int = DEFAULT_DELAY_SECONDS) -> None:
    """
    Process chunks until target percentage is reached.
    
    Args:
        batch_size: Number of chunks to process per batch
        target_percentage: Target percentage of completion
        delay_seconds: Delay between batches in seconds
    """
    from app import app  # Import Flask app
    
    logger.info(f"Starting background chunk processing to {target_percentage}% completion")
    logger.info(f"Using batch size of {batch_size} with {delay_seconds}s delay")
    
    batch_num = 1
    total_processed = 0
    
    # Use Flask app context for database operations
    with app.app_context():
        try:
            while True:
                # Get current progress
                progress_info = get_progress()
                current_percentage = progress_info['progress_percentage']
                
                # Log progress information
                logger.info(f"Vector store:   {progress_info['processed_count']} chunks")
                logger.info(f"Database:       {progress_info['total_chunks']} chunks in {progress_info['total_documents']} documents")
                logger.info(f"----------------------------------------")
                logger.info(f"Progress:       {progress_info['processed_count']}/{progress_info['total_chunks']} chunks")
                logger.info(f"                {current_percentage:.1f}% complete")
                logger.info(f"Remaining:      {progress_info['remaining_chunks']} chunks")
                logger.info(f"Est. time:      {progress_info['est_hours']}h {progress_info['est_minutes']}m remaining")
                logger.info(f"========================================")
                
                # Check if we've reached our target
                if current_percentage >= target_percentage:
                    logger.info(f"Target percentage of {target_percentage}% reached ({current_percentage:.1f}%)")
                    logger.info(f"Total processed: {total_processed} chunks")
                    break
                    
                # Get the next batch of chunks to process
                processed_chunk_ids = progress_info['processed_chunk_ids']
                chunks = get_next_chunk_batch(batch_size, processed_chunk_ids)
                
                if not chunks:
                    logger.info("No more chunks to process")
                    break
                    
                # Process the batch
                logger.info(f"Processing batch #{batch_num} with {len(chunks)} chunks")
                batch_results = process_batch(chunks)
                
                # Update counters and log results
                total_processed += batch_results['success_count']
                logger.info(f"Processed {batch_results['success_count']}/{len(chunks)} chunks in batch #{batch_num}")
                
                # Wait before next batch
                logger.info(f"Waiting {delay_seconds} seconds before next batch...")
                time.sleep(delay_seconds)
                
                batch_num += 1
                
        except KeyboardInterrupt:
            logger.info("Process interrupted by user")
        except Exception as e:
            logger.error(f"Error processing chunks: {str(e)}")
        finally:
            logger.info(f"Processing complete. Total processed: {total_processed} chunks")

def main():
    """Main function to parse arguments and start processing."""
    parser = argparse.ArgumentParser(description='Process chunks until target percentage is reached')
    parser.add_argument('--target', type=float, default=DEFAULT_TARGET_PERCENTAGE,
                       help=f'Target percentage of completion (default: {DEFAULT_TARGET_PERCENTAGE})')
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE,
                       help=f'Number of chunks to process per batch (default: {DEFAULT_BATCH_SIZE})')
    parser.add_argument('--delay', type=int, default=DEFAULT_DELAY_SECONDS,
                       help=f'Delay between batches in seconds (default: {DEFAULT_DELAY_SECONDS})')
    args = parser.parse_args()
    
    logger.info(f"Running process_chunks_background.py with batch size {args.batch_size}")
    logger.info(f"Process started with PID: {os.getpid()}")
    
    # Create a PID file to help monitor the process
    with open('process_chunks_background.pid', 'w') as f:
        f.write(str(os.getpid()))
    
    try:
        process_chunks_background(args.batch_size, args.target, args.delay)
    finally:
        # Remove PID file when done
        if os.path.exists('process_chunks_background.pid'):
            os.remove('process_chunks_background.pid')

if __name__ == '__main__':
    main()