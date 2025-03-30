#!/usr/bin/env python
"""
Process chunks until 50% target is reached

This script processes document chunks in batches until 50% of the total chunks are processed.
It includes automatic backups and progress tracking.
"""

import os
import sys
import time
import random
import logging
import pickle
import signal
import atexit
from datetime import datetime
from typing import Dict, Any, List, Set, Optional, Tuple, Union

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("process_to_50_percent.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Configuration
TARGET_PERCENTAGE = 50.0  # Process until 50% of chunks are processed
BATCH_SIZE = 5  # Number of chunks to process in a batch
MAX_RETRIES = 3  # Maximum number of retries for a chunk
BACKUP_INTERVAL = 20  # Number of chunks to process before making a backup
DELAY_BETWEEN_BATCHES = 5  # Seconds to wait between batches
PID_FILE = "process_50_percent.pid"  # PID file to check if process is running

# Import necessary modules
try:
    sys.path.append('.')
    from utils.vector_store import VectorStore
    from utils.llm_service import get_embedding
    from models import DocumentChunk, Document, db
except ImportError as e:
    logger.error(f"Failed to import modules: {e}")
    sys.exit(1)


def write_pid_file():
    """Write the current process ID to a file."""
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))


def remove_pid_file():
    """Remove the PID file when the process exits."""
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)


def get_processed_chunk_ids() -> Set[int]:
    """
    Get IDs of chunks that have already been processed.
    
    Returns:
        Set of chunk IDs that are already in the vector store
    """
    try:
        vector_store = VectorStore()
        processed_ids = set()
        
        if vector_store and hasattr(vector_store, 'documents'):
            for doc_id, doc in vector_store.documents.items():
                chunk_id = doc.get('metadata', {}).get('chunk_id')
                if chunk_id:
                    processed_ids.add(int(chunk_id))
        
        logger.info(f"Found {len(processed_ids)} processed chunk IDs in vector store")
        return processed_ids
    except Exception as e:
        logger.error(f"Error getting processed chunk IDs: {e}")
        return set()


def get_total_chunks_count() -> int:
    """
    Get the total number of chunks in the database.
    
    Returns:
        Total number of chunks
    """
    try:
        from app import app
        with app.app_context():
            return db.session.query(DocumentChunk).count()
    except Exception as e:
        logger.error(f"Error getting total chunks count: {e}")
        return 0


def get_progress() -> Dict[str, Any]:
    """
    Get the current progress of processing.
    
    Returns:
        Dictionary with progress information
    """
    processed_ids = get_processed_chunk_ids()
    total_chunks = get_total_chunks_count()
    
    if total_chunks == 0:
        percentage = 0.0
    else:
        percentage = (len(processed_ids) / total_chunks) * 100.0
    
    return {
        'processed_chunks': len(processed_ids),
        'total_chunks': total_chunks,
        'percentage': percentage,
        'target_percentage': TARGET_PERCENTAGE
    }


def get_next_chunk_batch(processed_ids: Set[int], batch_size: int = BATCH_SIZE) -> List[DocumentChunk]:
    """
    Get the next batch of chunks to process.
    
    Args:
        processed_ids: Set of chunk IDs that have already been processed
        batch_size: Number of chunks to retrieve
        
    Returns:
        List of DocumentChunk objects
    """
    try:
        from app import app
        with app.app_context():
            # Query for chunks that haven't been processed yet
            unprocessed_chunks = (
                db.session.query(DocumentChunk)
                .filter(~DocumentChunk.id.in_(processed_ids))
                .limit(batch_size)
                .all()
            )
            
            logger.info(f"Retrieved {len(unprocessed_chunks)} unprocessed chunks")
            return unprocessed_chunks
    except Exception as e:
        logger.error(f"Error getting next chunk batch: {e}")
        return []


def backup_vector_store():
    """
    Create a backup of the vector store.
    
    Returns:
        True if successful, False otherwise
    """
    try:
        os.system("python backup_vector_store.py")
        logger.info("Created vector store backup")
        return True
    except Exception as e:
        logger.error(f"Error creating vector store backup: {e}")
        return False


def process_chunk(chunk: DocumentChunk) -> bool:
    """
    Process a single chunk and add it to the vector store.
    
    Args:
        chunk: The DocumentChunk object to process
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Initialize services
        vector_store = VectorStore()
        
        # Get text from chunk
        text = chunk.text_content
        if not text:
            logger.warning(f"Empty text for chunk ID {chunk.id}, skipping")
            return False
        
        # Get metadata
        document = chunk.document
        if not document:
            logger.warning(f"No document found for chunk ID {chunk.id}, skipping")
            return False
        
        metadata = {
            'document_id': document.id,
            'chunk_id': chunk.id,
            'url': document.source_url,
            'title': document.title,
            'author': document.authors,
            'publication_year': document.publication_year,
            'doi': document.doi,
            'chunk_index': chunk.chunk_index
        }
        
        # Generate embedding
        embedding = get_embedding(text)
        if embedding is None:
            logger.error(f"Failed to generate embedding for chunk ID {chunk.id}")
            return False
        
        # Add to vector store 
        doc_id = vector_store.add_embedding(text, embedding, metadata)
        if not doc_id:
            logger.error(f"Failed to add chunk ID {chunk.id} to vector store")
            return False
        
        # Save the vector store
        vector_store.save()
        
        logger.info(f"Successfully processed chunk ID {chunk.id}")
        return True
    except Exception as e:
        logger.error(f"Error processing chunk ID {chunk.id}: {e}")
        return False


def process_batch(chunks: List[DocumentChunk]) -> Dict[str, Any]:
    """
    Process a batch of chunks.
    
    Args:
        chunks: List of DocumentChunk objects to process
        
    Returns:
        Dictionary with processing results
    """
    results = {
        'total': len(chunks),
        'successful': 0,
        'failed': 0,
        'details': []
    }
    
    for chunk in chunks:
        success = False
        retries = 0
        
        while not success and retries < MAX_RETRIES:
            if retries > 0:
                logger.info(f"Retrying chunk ID {chunk.id} (attempt {retries+1})")
                time.sleep(random.uniform(1, 3))  # Random backoff
            
            success = process_chunk(chunk)
            retries += 1
        
        if success:
            results['successful'] += 1
            results['details'].append({
                'chunk_id': chunk.id,
                'success': True,
                'retries': retries
            })
        else:
            results['failed'] += 1
            results['details'].append({
                'chunk_id': chunk.id,
                'success': False,
                'retries': retries
            })
    
    return results


def run_until_target() -> bool:
    """
    Process chunks in batches until the target percentage is reached.
    
    Returns:
        True if target reached successfully, False otherwise
    """
    processed_count = 0
    
    while True:
        # Get current progress
        progress = get_progress()
        logger.info(f"Current progress: {progress['percentage']:.2f}% ({progress['processed_chunks']}/{progress['total_chunks']})")
        
        # Check if target reached
        if progress['percentage'] >= TARGET_PERCENTAGE:
            logger.info(f"🎉 Target percentage {TARGET_PERCENTAGE}% reached! Processing complete.")
            return True
        
        # Get next batch of chunks
        processed_ids = get_processed_chunk_ids()
        chunks = get_next_chunk_batch(processed_ids)
        
        if not chunks:
            logger.warning("No more chunks to process, but target not reached")
            return False
        
        # Process batch
        logger.info(f"Processing batch of {len(chunks)} chunks")
        results = process_batch(chunks)
        logger.info(f"Batch results: {results['successful']} successful, {results['failed']} failed")
        
        # Update processed count
        processed_count += results['successful']
        
        # Create backup if needed
        if processed_count % BACKUP_INTERVAL == 0:
            backup_vector_store()
        
        # Delay between batches
        time.sleep(DELAY_BETWEEN_BATCHES)


def handle_exit(*args):
    """Handle exit signals by creating a final backup."""
    logger.info("Received exit signal, creating final backup...")
    backup_vector_store()
    remove_pid_file()
    logger.info("Final backup created, exiting")
    sys.exit(0)


def main():
    """Main function to run the processing."""
    logger.info(f"Starting processing to {TARGET_PERCENTAGE}% target")
    
    # Register signal handlers
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    atexit.register(remove_pid_file)
    
    # Write PID file
    write_pid_file()
    
    # Create initial backup
    backup_vector_store()
    
    # Run until target reached
    success = run_until_target()
    
    # Create final backup
    backup_vector_store()
    
    # Remove PID file
    remove_pid_file()
    
    if success:
        logger.info("Processing completed successfully")
        return 0
    else:
        logger.warning("Processing finished but target not reached")
        return 1


if __name__ == "__main__":
    sys.exit(main())