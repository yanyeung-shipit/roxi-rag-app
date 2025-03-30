#!/usr/bin/env python3
"""
Improved Continuous Processor

This script is a streamlined and improved version of the continuous chunk processor.
It's designed to be more efficient and reliable in the Replit environment.

Key features:
- Direct database access with no ORM overhead
- Simplified vector store operations
- Configurable batch size and delays
- Progress tracking and reporting
- Checkpoint-based resumption
"""

import os
import sys
import time
import json
import logging
import datetime
import pickle
import argparse
from typing import Dict, List, Set, Any, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("improved_processor.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

try:
    import faiss
    from tenacity import retry, stop_after_attempt, wait_fixed
    import numpy as np
    import psycopg2
    from psycopg2.extras import RealDictCursor
    import openai
except ImportError as e:
    logger.error(f"Failed to import required modules: {e}")
    sys.exit(1)

# Configuration constants
DEFAULT_BATCH_SIZE = 1
DEFAULT_DELAY = 3  # seconds between operations
DEFAULT_TARGET_PERCENTAGE = 40.0
DEFAULT_MAX_CHUNKS = None  # Process all chunks by default
CHECKPOINT_FILE = "processor_checkpoint.json"
VECTOR_DATA_FILE = "document_data.pkl"
FAISS_INDEX_FILE = "faiss_index.bin"

# OpenAI configuration
openai.api_key = os.environ.get("OPENAI_API_KEY")
EMBEDDING_MODEL = "text-embedding-3-small"

# Database connection
DB_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    """Get a connection to the PostgreSQL database."""
    try:
        return psycopg2.connect(DB_URL)
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise


def get_embeddings(text: str) -> List[float]:
    """
    Get embeddings for text using OpenAI's API.
    
    Args:
        text: The text to embed
        
    Returns:
        List of embedding values
    """
    try:
        response = openai.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
            dimensions=1536
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Error getting embeddings: {e}")
        raise


def load_vector_store() -> Tuple[Dict[str, Any], Any]:
    """
    Load the vector store data from disk.
    
    Returns:
        Tuple containing (document data, FAISS index)
    """
    # Load document data
    try:
        with open(VECTOR_DATA_FILE, 'rb') as f:
            document_data = pickle.load(f)
        logger.info(f"Loaded document data from {VECTOR_DATA_FILE}")
    except FileNotFoundError:
        document_data = {"documents": {}, "id_to_uuid": {}, "next_id": 0}
        logger.info("No existing document data found, initializing new store")
    
    # Load FAISS index
    try:
        index = faiss.read_index(FAISS_INDEX_FILE)
        logger.info(f"Loaded FAISS index from {FAISS_INDEX_FILE}")
    except:
        # Initialize a new index
        dimension = 1536  # For OpenAI embeddings
        index = faiss.IndexFlatL2(dimension)
        logger.info("No existing FAISS index found, initializing new index")
    
    return document_data, index


def save_vector_store(document_data: Dict[str, Any], index: Any) -> None:
    """
    Save the vector store data to disk.
    
    Args:
        document_data: The document data dictionary
        index: The FAISS index
    """
    try:
        # Save document data
        with open(VECTOR_DATA_FILE, 'wb') as f:
            pickle.dump(document_data, f)
        
        # Save FAISS index
        faiss.write_index(index, FAISS_INDEX_FILE)
        
        logger.info("Vector store saved to disk")
    except Exception as e:
        logger.error(f"Error saving vector store: {e}")
        raise


def get_processed_chunk_ids(document_data: Dict[str, Any]) -> Set[int]:
    """
    Get IDs of chunks that have already been processed.
    
    Args:
        document_data: The document data dictionary
        
    Returns:
        Set of processed chunk IDs
    """
    processed_ids = set()
    
    for doc_id, doc in document_data["documents"].items():
        if "chunk_id" in doc:
            processed_ids.add(doc["chunk_id"])
    
    logger.info(f"Found {len(processed_ids)} processed chunk IDs in vector store")
    return processed_ids


def save_checkpoint(processed_ids: Set[int]) -> None:
    """
    Save the current state of processed chunk IDs.
    
    Args:
        processed_ids: Set of processed chunk IDs
    """
    try:
        with open(CHECKPOINT_FILE, 'w') as f:
            json.dump({
                "processed_ids": list(processed_ids),
                "timestamp": datetime.datetime.now().isoformat()
            }, f)
        logger.info(f"Saved checkpoint with {len(processed_ids)} processed chunks")
    except Exception as e:
        logger.error(f"Error saving checkpoint: {e}")


def load_checkpoint() -> Set[int]:
    """
    Load the previous checkpoint if it exists.
    
    Returns:
        Set of processed chunk IDs from checkpoint
    """
    try:
        with open(CHECKPOINT_FILE, 'r') as f:
            data = json.load(f)
            processed_ids = set(data["processed_ids"])
            logger.info(f"Loaded checkpoint with {len(processed_ids)} processed chunks from {data['timestamp']}")
            return processed_ids
    except FileNotFoundError:
        logger.info("No checkpoint file found, starting fresh")
        return set()
    except Exception as e:
        logger.error(f"Error loading checkpoint: {e}")
        return set()


def get_unprocessed_chunks(processed_ids: Set[int], batch_size: int) -> List[Dict[str, Any]]:
    """
    Get chunks that haven't been processed yet.
    
    Args:
        processed_ids: Set of already processed chunk IDs
        batch_size: Number of chunks to retrieve
        
    Returns:
        List of chunk dictionaries
    """
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            placeholders = ','.join(['%s'] * len(processed_ids)) if processed_ids else '0'
            
            query = f"""
            SELECT c.id as chunk_id, c.text_content as content, c.document_id, 
                   d.title as document_title, d.source_url as document_url,
                   d.title as document_description, d.filename
            FROM document_chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.id NOT IN ({placeholders})
            ORDER BY c.document_id, c.id
            LIMIT %s
            """
            
            if processed_ids:
                cur.execute(query, (list(processed_ids) + [batch_size]))
            else:
                # If no processed IDs yet, use a simpler query
                cur.execute(
                    """
                    SELECT c.id as chunk_id, c.text_content as content, c.document_id, 
                           d.title as document_title, d.source_url as document_url,
                           d.title as document_description, d.filename
                    FROM document_chunks c
                    JOIN documents d ON c.document_id = d.id
                    ORDER BY c.document_id, c.id
                    LIMIT %s
                    """,
                    (batch_size,)
                )
            
            chunks = list(cur.fetchall())
            
        conn.close()
        logger.info(f"Retrieved {len(chunks)} unprocessed chunks")
        return chunks
    except Exception as e:
        logger.error(f"Error getting unprocessed chunks: {e}")
        raise


def get_total_chunks_count() -> int:
    """
    Get the total number of chunks in the database.
    
    Returns:
        Total number of chunks
    """
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM document_chunks")
            count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logger.error(f"Error getting total chunks count: {e}")
        return 0


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def process_chunk(chunk: Dict[str, Any], document_data: Dict[str, Any], index: Any) -> bool:
    """
    Process a single chunk and add it to the vector store.
    
    Args:
        chunk: The chunk dictionary
        document_data: The document data dictionary
        index: The FAISS index
        
    Returns:
        True if successful, False otherwise
    """
    try:
        chunk_id = chunk["chunk_id"]
        document_id = chunk["document_id"]
        content = chunk["content"]
        
        # Get embedding for the content
        embedding = get_embeddings(content)
        
        # Create document entry
        doc_entry = {
            "document_id": document_id,
            "chunk_id": chunk_id,
            "page_content": content,
            "metadata": {
                "title": chunk["document_title"],
                "url": chunk["document_url"],
                "description": chunk["document_description"],
                "filename": chunk["filename"],
                "source_id": str(document_id),
                "chunk_id": chunk_id
            }
        }
        
        # Add to document data
        next_id = document_data["next_id"]
        document_data["documents"][str(next_id)] = doc_entry
        document_data["id_to_uuid"][str(next_id)] = str(next_id)
        document_data["next_id"] = next_id + 1
        
        # Add embedding to index
        embedding_array = np.array([embedding], dtype=np.float32)
        index.add(embedding_array)
        
        logger.info(f"Successfully processed chunk {chunk_id} from document {document_id}")
        return True
    except Exception as e:
        logger.error(f"Error processing chunk {chunk_id}: {e}")
        return False


def get_progress(processed_count: int, total_count: int) -> Dict[str, Any]:
    """
    Get the current progress information.
    
    Args:
        processed_count: Number of processed chunks
        total_count: Total number of chunks
        
    Returns:
        Dictionary with progress information
    """
    percentage = (processed_count / total_count * 100) if total_count > 0 else 0
    return {
        "processed_chunks": processed_count,
        "total_chunks": total_count,
        "percentage": round(percentage, 2),
        "remaining": total_count - processed_count,
        "timestamp": datetime.datetime.now().isoformat()
    }


def print_progress_info(progress: Dict[str, Any]) -> None:
    """
    Print progress information to the console.
    
    Args:
        progress: Progress information dictionary
    """
    logger.info(f"Progress: {progress['processed_chunks']}/{progress['total_chunks']} chunks ({progress['percentage']}%)")
    logger.info(f"Remaining: {progress['remaining']} chunks")


def process_chunks(batch_size: int = DEFAULT_BATCH_SIZE, 
                  delay: int = DEFAULT_DELAY,
                  target_percentage: float = DEFAULT_TARGET_PERCENTAGE,
                  max_chunks: Optional[int] = DEFAULT_MAX_CHUNKS) -> None:
    """
    Process chunks in batches until target percentage is reached or max_chunks is hit.
    
    Args:
        batch_size: Number of chunks to process per batch
        delay: Delay in seconds between chunk processing
        target_percentage: Stop when this percentage is reached
        max_chunks: Maximum number of chunks to process (None for unlimited)
    """
    # Load vector store
    document_data, index = load_vector_store()
    
    # Get processed chunk IDs from the vector store
    processed_ids = get_processed_chunk_ids(document_data)
    
    # Load checkpoint if available
    checkpoint_ids = load_checkpoint()
    
    # Merge processed IDs from vector store and checkpoint
    processed_ids = processed_ids.union(checkpoint_ids)
    
    # Get total number of chunks
    total_chunks = get_total_chunks_count()
    
    # Track processing statistics
    stats = {
        "start_time": datetime.datetime.now(),
        "chunks_processed": 0,
        "successful": 0,
        "failed": 0
    }
    
    # Main processing loop
    processed_count = len(processed_ids)
    chunks_processed_this_session = 0
    
    while True:
        # Get current progress
        progress = get_progress(processed_count, total_chunks)
        print_progress_info(progress)
        
        # Check if we've reached the target percentage
        if progress["percentage"] >= target_percentage:
            logger.info(f"Target percentage of {target_percentage}% reached, stopping")
            break
        
        # Check if we've processed the maximum number of chunks
        if max_chunks is not None and chunks_processed_this_session >= max_chunks:
            logger.info(f"Maximum number of chunks ({max_chunks}) processed, stopping")
            break
        
        # Get batch of unprocessed chunks
        chunks = get_unprocessed_chunks(processed_ids, batch_size)
        
        if not chunks:
            logger.info("No more unprocessed chunks found, stopping")
            break
        
        # Process each chunk in the batch
        for chunk in chunks:
            chunk_id = chunk["chunk_id"]
            
            # Skip if already processed
            if chunk_id in processed_ids:
                continue
            
            # Process the chunk
            success = process_chunk(chunk, document_data, index)
            
            if success:
                processed_ids.add(chunk_id)
                processed_count += 1
                stats["successful"] += 1
            else:
                stats["failed"] += 1
            
            stats["chunks_processed"] += 1
            chunks_processed_this_session += 1
            
            # Save vector store and checkpoint after each chunk to prevent data loss
            save_vector_store(document_data, index)
            save_checkpoint(processed_ids)
            
            # Check if we've reached the target or max chunks after each individual chunk
            progress = get_progress(processed_count, total_chunks)
            if progress["percentage"] >= target_percentage:
                logger.info(f"Target percentage of {target_percentage}% reached, stopping")
                break
                
            if max_chunks is not None and chunks_processed_this_session >= max_chunks:
                logger.info(f"Maximum number of chunks ({max_chunks}) processed, stopping")
                break
            
            # Delay between chunks to prevent Replit from killing the process
            if delay > 0:
                time.sleep(delay)
        
        # If we've processed all chunks in the batch, get the next batch
        if not chunks:
            logger.info("No more unprocessed chunks found, stopping")
            break
    
    # Print final statistics
    end_time = datetime.datetime.now()
    duration = (end_time - stats["start_time"]).total_seconds()
    logger.info(f"Processing completed in {duration:.2f} seconds")
    logger.info(f"Chunks processed: {stats['chunks_processed']}")
    logger.info(f"Successful: {stats['successful']}")
    logger.info(f"Failed: {stats['failed']}")
    
    # Final progress
    progress = get_progress(processed_count, total_chunks)
    print_progress_info(progress)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Process chunks and add to vector store")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                        help=f"Number of chunks to process per batch (default: {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--delay", type=int, default=DEFAULT_DELAY,
                        help=f"Delay in seconds between chunk processing (default: {DEFAULT_DELAY})")
    parser.add_argument("--target", type=float, default=DEFAULT_TARGET_PERCENTAGE,
                        help=f"Target percentage of completion (default: {DEFAULT_TARGET_PERCENTAGE})")
    parser.add_argument("--max-chunks", type=int, default=DEFAULT_MAX_CHUNKS,
                        help=f"Maximum number of chunks to process (default: unlimited)")
    
    args = parser.parse_args()
    
    logger.info(f"Starting chunk processor with batch size {args.batch_size}, "
                f"delay {args.delay}s, target {args.target}%")
    
    try:
        process_chunks(
            batch_size=args.batch_size,
            delay=args.delay,
            target_percentage=args.target,
            max_chunks=args.max_chunks
        )
        logger.info("Processing completed successfully")
    except KeyboardInterrupt:
        logger.info("Processing interrupted by user")
    except Exception as e:
        logger.error(f"Processing failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()