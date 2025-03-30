"""
Fast Chunk Processor - Optimized for Replit environment

This script processes chunks in small batches with proper delays between operations
to prevent timeouts and memory issues in the Replit environment.
"""

import logging
import os
import time
import pickle
from typing import List, Dict, Any, Set, Optional
import sys

from models import DocumentChunk, db
from utils.vector_store import VectorStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
DEFAULT_BATCH_SIZE = 3  # Small batch size for stability
DELAY_BETWEEN_CHUNKS = 2  # seconds
DELAY_BETWEEN_BATCHES = 5  # seconds
CHECKPOINT_FILE = "processed_chunk_ids.checkpoint"

def get_vector_store() -> VectorStore:
    """Get the vector store instance."""
    return VectorStore()

def get_processed_chunk_ids() -> Set[int]:
    """Get IDs of chunks that have already been processed."""
    vector_store = get_vector_store()
    processed_ids = set()
    
    for doc in vector_store.documents:
        if hasattr(doc.metadata, 'chunk_id') and doc.metadata.chunk_id:
            processed_ids.add(doc.metadata.chunk_id)
    
    logger.info(f"Found {len(processed_ids)} processed chunks in vector store")
    return processed_ids

def save_checkpoint(processed_ids: Set[int]) -> None:
    """Save the current state of processed chunk IDs."""
    with open(CHECKPOINT_FILE, 'wb') as f:
        pickle.dump(processed_ids, f)
    logger.info(f"Saved checkpoint with {len(processed_ids)} processed chunks")

def load_checkpoint() -> Set[int]:
    """Load the previous checkpoint if it exists."""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'rb') as f:
            processed_ids = pickle.load(f)
        logger.info(f"Loaded checkpoint with {len(processed_ids)} processed chunks")
        return processed_ids
    return set()

def get_next_chunk_batch(batch_size: int, processed_ids: Set[int]) -> List[DocumentChunk]:
    """Get the next batch of chunks to process."""
    # Find chunks that haven't been processed yet
    chunks = (DocumentChunk.query
              .filter(~DocumentChunk.id.in_(processed_ids))
              .limit(batch_size)
              .all())
    
    if chunks:
        logger.info(f"Found {len(chunks)} unprocessed chunks")
    else:
        logger.info("No more unprocessed chunks found")
    
    return chunks

def process_chunk(chunk: DocumentChunk) -> bool:
    """Process a single chunk and add it to the vector store."""
    try:
        from utils.openai_service import OpenAIEmbeddingService
        vector_store = get_vector_store()
        embedding_service = OpenAIEmbeddingService()
        
        # Get embedding for the text
        try:
            embedding = embedding_service.get_embedding(chunk.text)
        except Exception as e:
            logger.error(f"Error generating embedding for chunk {chunk.id}: {str(e)}")
            return False
        
        # Create metadata object
        metadata = {
            'chunk_id': chunk.id,
            'document_id': chunk.document_id,
            'source': chunk.source or "Unknown",
            'title': chunk.title or "Untitled",
            'url': chunk.url,
            'filename': chunk.filename,
            'page': chunk.page_number,
            'chunk_index': chunk.chunk_index,
            'citation': chunk.citation or "",
            'doi': chunk.doi or "",
            'authors': chunk.authors or "",
            'publication_date': str(chunk.publication_date) if chunk.publication_date else "",
            'journal': chunk.journal or "",
        }
        
        # Add to vector store with embedding
        vector_store.add_embedding(
            text=chunk.text,
            embedding=embedding,
            metadata=metadata
        )
        
        # Save after each chunk to ensure we don't lose progress
        vector_store.save()
        
        return True
    except Exception as e:
        logger.error(f"Error processing chunk {chunk.id}: {str(e)}")
        return False

def process_batch(chunks: List[DocumentChunk], processed_ids: Set[int]) -> Dict[str, Any]:
    """Process a batch of chunks."""
    results = {
        'successful': 0,
        'failed': 0,
        'processed_ids': []
    }
    
    for chunk in chunks:
        logger.info(f"Processing chunk {chunk.id} from document {chunk.document_id}")
        
        success = process_chunk(chunk)
        
        if success:
            results['successful'] += 1
            results['processed_ids'].append(chunk.id)
            processed_ids.add(chunk.id)
        else:
            results['failed'] += 1
        
        # Delay between chunks to prevent rate limiting
        time.sleep(DELAY_BETWEEN_CHUNKS)
    
    # Save processed IDs checkpoint
    save_checkpoint(processed_ids)
    
    return results

def get_progress() -> Dict[str, Any]:
    """Get the current progress of vector store rebuilding."""
    vector_store = get_vector_store()
    
    # Count documents in vector store
    vector_count = len(vector_store.documents)
    
    # Count chunks in database
    with db.session() as session:
        total_chunks = session.query(DocumentChunk).count()
        total_docs = len(set(c.document_id for c in session.query(DocumentChunk.document_id).all()))
    
    # Calculate percentage
    percentage = (vector_count / total_chunks * 100) if total_chunks > 0 else 0
    
    # Calculate estimated time remaining (very rough estimate)
    remaining_chunks = total_chunks - vector_count
    # Assume 3 seconds per chunk
    seconds_per_chunk = 3
    estimated_seconds = remaining_chunks * seconds_per_chunk
    
    hours, remainder = divmod(estimated_seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    
    return {
        'vector_count': vector_count,
        'total_chunks': total_chunks,
        'total_documents': total_docs,
        'percentage': round(percentage, 1),
        'remaining_chunks': remaining_chunks,
        'estimated_hours': int(hours),
        'estimated_minutes': int(minutes)
    }

def print_progress_info(progress: Dict[str, Any]) -> None:
    """Print progress information."""
    logger.info("=" * 40)
    logger.info("VECTOR STORE REBUILD PROGRESS")
    logger.info("=" * 40)
    logger.info(f"Vector store:   {progress['vector_count']} chunks")
    logger.info(f"Database:       {progress['total_chunks']} chunks in {progress['total_documents']} documents")
    logger.info("-" * 40)
    logger.info(f"Progress:       {progress['vector_count']}/{progress['total_chunks']} chunks")
    logger.info(f"                {progress['percentage']}% complete")
    logger.info(f"Remaining:      {progress['remaining_chunks']} chunks")
    logger.info(f"Est. time:      {progress['estimated_hours']}h {progress['estimated_minutes']}m remaining")
    logger.info("=" * 40)

def process_chunks(batch_size: int = DEFAULT_BATCH_SIZE, target_percentage: float = 75.0, 
                 max_batches: Optional[int] = None) -> None:
    """
    Process chunks in batches until target percentage is reached or max_batches is hit.
    
    Args:
        batch_size: Number of chunks to process per batch
        target_percentage: Stop when this percentage is reached
        max_batches: Maximum number of batches to process (None for unlimited)
    """
    # Initialize
    processed_ids = get_processed_chunk_ids()
    # Load checkpoint to supplement the processed IDs
    checkpoint_ids = load_checkpoint()
    processed_ids.update(checkpoint_ids)
    
    batches_processed = 0
    
    # Get initial progress
    progress = get_progress()
    print_progress_info(progress)
    
    # Process batches until we reach our target percentage
    while progress['percentage'] < target_percentage:
        if max_batches is not None and batches_processed >= max_batches:
            logger.info(f"Reached maximum number of batches ({max_batches}), stopping")
            break
            
        logger.info(f"Starting batch {batches_processed + 1}")
        
        # Get next batch of chunks
        chunks = get_next_chunk_batch(batch_size, processed_ids)
        
        if not chunks:
            logger.info("No more chunks to process")
            break
        
        # Process the batch
        batch_results = process_batch(chunks, processed_ids)
        logger.info(f"Batch results: {batch_results['successful']} successful, {batch_results['failed']} failed")
        
        # Update progress
        progress = get_progress()
        print_progress_info(progress)
        
        batches_processed += 1
        
        # Delay between batches
        if progress['percentage'] < target_percentage:
            logger.info(f"Sleeping for {DELAY_BETWEEN_BATCHES} seconds before next batch")
            time.sleep(DELAY_BETWEEN_BATCHES)
    
    logger.info(f"Processing complete. Processed {batches_processed} batches.")
    final_progress = get_progress()
    print_progress_info(final_progress)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Process chunks and add them to the vector store")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, 
                      help=f"Number of chunks to process per batch (default: {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--target", type=float, default=75.0,
                      help="Target percentage to reach (default: 75.0)")
    parser.add_argument("--max-batches", type=int, default=None,
                      help="Maximum number of batches to process (default: unlimited)")
    
    args = parser.parse_args()
    
    try:
        process_chunks(batch_size=args.batch_size, target_percentage=args.target, 
                     max_batches=args.max_batches)
    except KeyboardInterrupt:
        logger.info("Processing interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error during processing: {str(e)}")
        sys.exit(1)