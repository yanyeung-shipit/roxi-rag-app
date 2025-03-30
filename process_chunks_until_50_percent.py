#!/usr/bin/env python3
"""
Script to process chunks until reaching 50% completion.
This script handles its own logging and will continue until the target is reached.
"""

import logging
import os
import random
import sys
import time
from typing import Dict, Any, List, Set, Tuple, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('process_until_50_percent.log')
    ]
)
logger = logging.getLogger(__name__)

# Configuration
TARGET_PERCENTAGE = 50.0
BATCH_SIZE = 5
DELAY_BETWEEN_BATCHES = 1
MAX_RETRIES = 3
BACKUP_INTERVAL = 10

def get_processed_chunk_ids() -> Set[int]:
    """
    Get IDs of chunks that have already been processed.
    
    Returns:
        Set of chunk IDs that are already in the vector store
    """
    try:
        from utils.vector_store import VectorStore
        
        # Initialize vector store and get processed chunk IDs
        vector_store = VectorStore()
        processed_ids = set()
        
        # Extract chunk IDs from vector store
        for doc_id, doc in vector_store.documents.items():
            metadata = doc.get('metadata', {})
            if metadata and 'chunk_id' in metadata:
                chunk_id = metadata['chunk_id']
                if isinstance(chunk_id, int):
                    processed_ids.add(chunk_id)
        
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
        from models import DocumentChunk
        from app import app, db
        
        with app.app_context():
            total_chunks = db.session.query(DocumentChunk).count()
            return total_chunks
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
        percentage = 0
    else:
        percentage = (len(processed_ids) / total_chunks) * 100
    
    return {
        'processed_chunks': len(processed_ids),
        'total_chunks': total_chunks,
        'percentage': percentage,
        'target_percentage': TARGET_PERCENTAGE
    }

def get_next_chunk_batch(processed_ids: Set[int], batch_size: int = BATCH_SIZE) -> List[Tuple[Any, Any]]:
    """
    Get the next batch of chunks to process with their parent documents.
    
    Args:
        processed_ids: Set of chunk IDs that have already been processed
        batch_size: Number of chunks to retrieve
        
    Returns:
        List of tuples (DocumentChunk, Document) containing both chunk and document
    """
    try:
        from models import DocumentChunk, Document
        from app import app, db
        
        with app.app_context():
            # Join query to get both chunks and their documents in a single query
            # This avoids lazy loading issues
            unprocessed_chunks = (
                db.session.query(DocumentChunk, Document)
                .join(Document, DocumentChunk.document_id == Document.id)
                .filter(~DocumentChunk.id.in_(processed_ids))
                .limit(batch_size)
                .all()
            )
            
            logger.info(f"Retrieved {len(unprocessed_chunks)} unprocessed chunks with documents")
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

def process_chunk(chunk_tuple: Tuple[Any, Any]) -> bool:
    """
    Process a single chunk and its document and add it to the vector store.
    
    Args:
        chunk_tuple: A tuple containing (DocumentChunk, Document) objects
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Extract chunk and document from tuple
        chunk, document = chunk_tuple
        
        # Initialize services
        from utils.vector_store import VectorStore
        from utils.llm_service import get_embedding
        
        vector_store = VectorStore()
        
        # Get text from chunk
        text = chunk.text_content
        if not text:
            logger.warning(f"Empty text for chunk ID {chunk.id}, skipping")
            return False
        
        # Create metadata from chunk and document
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
        chunk_id = chunk_tuple[0].id if isinstance(chunk_tuple, tuple) and len(chunk_tuple) > 0 else "unknown"
        logger.error(f"Error processing chunk ID {chunk_id}: {e}")
        return False

def process_batch(chunks: List[Tuple[Any, Any]]) -> Dict[str, Any]:
    """
    Process a batch of chunks with their documents.
    
    Args:
        chunks: List of (DocumentChunk, Document) tuples to process
        
    Returns:
        Dictionary with processing results
    """
    results = {
        'total': len(chunks),
        'successful': 0,
        'failed': 0,
        'details': []
    }
    
    for chunk_tuple in chunks:
        chunk, _ = chunk_tuple  # Extract chunk for logging
        success = False
        retries = 0
        
        while not success and retries < MAX_RETRIES:
            if retries > 0:
                logger.info(f"Retrying chunk ID {chunk.id} (attempt {retries+1})")
                time.sleep(random.uniform(1, 3))  # Random backoff
            
            success = process_chunk(chunk_tuple)
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

def main():
    """Main function to run the processing."""
    logger.info(f"Starting processing until {TARGET_PERCENTAGE}% completion")
    
    # Create initial backup
    backup_vector_store()
    
    # Run until target reached
    success = run_until_target()
    
    # Create final backup
    backup_vector_store()
    
    if success:
        logger.info("Processing completed successfully")
        return 0
    else:
        logger.warning("Processing finished but target not reached")
        return 1

if __name__ == "__main__":
    sys.exit(main())