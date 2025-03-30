#!/usr/bin/env python3
"""
Simple, direct chunk processor for adding documents to vector store.
This is an ultra-simplified version designed to be reliable in Replit's environment.
"""

import os
import sys
import json
import pickle
import time
import logging
import datetime
from typing import Dict, List, Set, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("simple_processor.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Import required libraries
try:
    import numpy as np
    import faiss
    import psycopg2
    from psycopg2.extras import RealDictCursor
    import openai
except ImportError as e:
    logger.error(f"Failed to import required modules: {e}")
    sys.exit(1)

# Configuration
CHECKPOINT_FILE = "simple_processor_checkpoint.json"
VECTOR_DATA_FILE = "document_data.pkl"
FAISS_INDEX_FILE = "faiss_index.bin"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
DB_URL = os.environ.get("DATABASE_URL")
EMBEDDING_MODEL = "text-embedding-3-small"

# Initialize OpenAI client
openai.api_key = OPENAI_API_KEY

# Load vector store
def load_vector_store():
    """Load the vector store data and FAISS index."""
    try:
        # Load document data
        with open(VECTOR_DATA_FILE, 'rb') as f:
            document_data = pickle.load(f)
        
        # Make sure document_data has all the required keys
        if "documents" not in document_data:
            document_data["documents"] = {}
        if "id_to_uuid" not in document_data:
            document_data["id_to_uuid"] = {}
        if "next_id" not in document_data:
            if document_data["documents"]:
                # If there are already documents, find the highest ID and add 1
                max_id = max(int(k) for k in document_data["documents"].keys() if k.isdigit())
                document_data["next_id"] = max_id + 1
            else:
                document_data["next_id"] = 0
        
        logger.info(f"Loaded document data with {len(document_data.get('documents', {}))} documents")
        
        # Load FAISS index
        index = faiss.read_index(FAISS_INDEX_FILE)
        logger.info(f"Loaded FAISS index with {index.ntotal} vectors")
        
        return document_data, index
    except Exception as e:
        logger.error(f"Error loading vector store: {e}")
        # Return empty data structures if loading fails
        dimension = 1536  # OpenAI embedding dimension
        return {"documents": {}, "id_to_uuid": {}, "next_id": 0}, faiss.IndexFlatL2(dimension)

# Save vector store
def save_vector_store(document_data, index):
    """Save the vector store data and FAISS index."""
    try:
        # Create backup of existing data first
        if os.path.exists(VECTOR_DATA_FILE):
            backup_name = f"{VECTOR_DATA_FILE}.bak.{int(time.time())}"
            os.rename(VECTOR_DATA_FILE, backup_name)
            logger.info(f"Created backup of document data: {backup_name}")
        
        if os.path.exists(FAISS_INDEX_FILE):
            backup_name = f"{FAISS_INDEX_FILE}.bak.{int(time.time())}"
            os.rename(FAISS_INDEX_FILE, backup_name)
            logger.info(f"Created backup of FAISS index: {backup_name}")
        
        # Save new data
        with open(VECTOR_DATA_FILE, 'wb') as f:
            pickle.dump(document_data, f)
        
        faiss.write_index(index, FAISS_INDEX_FILE)
        
        logger.info("Vector store saved successfully")
        return True
    except Exception as e:
        logger.error(f"Error saving vector store: {e}")
        return False

# Get processed chunk IDs
def get_processed_chunks():
    """Get IDs of chunks that have already been processed."""
    try:
        # Try to load from checkpoint first
        if os.path.exists(CHECKPOINT_FILE):
            with open(CHECKPOINT_FILE, 'r') as f:
                data = json.load(f)
                processed_ids = set(data.get("processed_ids", []))
                logger.info(f"Loaded {len(processed_ids)} processed chunk IDs from checkpoint")
                return processed_ids
        
        # If no checkpoint, extract from vector store
        document_data, _ = load_vector_store()
        processed_ids = set()
        
        for doc_id, doc in document_data.get("documents", {}).items():
            if "chunk_id" in doc:
                processed_ids.add(doc["chunk_id"])
            elif "metadata" in doc and "chunk_id" in doc["metadata"]:
                processed_ids.add(doc["metadata"]["chunk_id"])
        
        logger.info(f"Extracted {len(processed_ids)} processed chunk IDs from vector store")
        return processed_ids
    except Exception as e:
        logger.error(f"Error getting processed chunks: {e}")
        return set()

# Save checkpoint
def save_checkpoint(processed_ids):
    """Save the current state of processed chunk IDs."""
    try:
        with open(CHECKPOINT_FILE, 'w') as f:
            json.dump({
                "processed_ids": list(processed_ids),
                "timestamp": datetime.datetime.now().isoformat()
            }, f)
        logger.info(f"Saved checkpoint with {len(processed_ids)} processed chunk IDs")
        return True
    except Exception as e:
        logger.error(f"Error saving checkpoint: {e}")
        return False

# Get a database connection
def get_db_connection():
    """Get a connection to the PostgreSQL database."""
    try:
        return psycopg2.connect(DB_URL)
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise

# Get total chunks count
def get_total_chunks_count():
    """Get the total number of chunks in the database."""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM document_chunks")
            count = cur.fetchone()[0]
        conn.close()
        logger.info(f"Total chunks in database: {count}")
        return count
    except Exception as e:
        logger.error(f"Error getting total chunks count: {e}")
        return 0

# Get next chunk to process
def get_next_chunk(processed_ids):
    """Get the next chunk to process."""
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
            LIMIT 1
            """
            
            if processed_ids:
                cur.execute(query, list(processed_ids))
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
                    LIMIT 1
                    """
                )
            
            chunk = cur.fetchone()
        
        conn.close()
        
        if chunk:
            logger.info(f"Retrieved chunk {chunk['chunk_id']} from document {chunk['document_id']}")
        else:
            logger.info("No more chunks to process")
            
        return chunk
    except Exception as e:
        logger.error(f"Error getting next chunk: {e}")
        return None

# Get embeddings for text
def get_embedding(text):
    """Get embedding for text using OpenAI's API."""
    try:
        response = openai.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
            dimensions=1536
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Error getting embedding: {e}")
        raise

# Process a single chunk
def process_chunk(chunk, document_data, index):
    """Process a single chunk and add it to the vector store."""
    try:
        chunk_id = chunk["chunk_id"]
        document_id = chunk["document_id"]
        content = chunk["content"]
        
        # Get embedding for the content
        embedding = get_embedding(content)
        
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
        logger.error(f"Error processing chunk: {e}")
        return False

# Get progress information
def get_progress(processed_count, total_count):
    """Get progress information."""
    percentage = (processed_count / total_count * 100) if total_count > 0 else 0
    return {
        "processed_chunks": processed_count,
        "total_chunks": total_count,
        "percentage": round(percentage, 2),
        "remaining": total_count - processed_count
    }

# Run processor
def run_processor(target_percentage=40.0, max_chunks=None, delay_seconds=3):
    """
    Run the chunk processor until target percentage or max chunks is reached.
    
    Args:
        target_percentage: Stop when this percentage of chunks is processed
        max_chunks: Maximum number of chunks to process (None for unlimited)
        delay_seconds: Delay between processing chunks
    """
    logger.info(f"Starting simple chunk processor with target {target_percentage}%, "
               f"max chunks {max_chunks}, delay {delay_seconds}s")
    
    # Load vector store
    document_data, index = load_vector_store()
    
    # Get processed chunk IDs
    processed_ids = get_processed_chunks()
    
    # Get total chunks count
    total_chunks = get_total_chunks_count()
    
    # Initialize stats
    stats = {
        "start_time": datetime.datetime.now(),
        "chunks_processed": 0,
        "successful": 0,
        "failed": 0
    }
    
    processed_count = len(processed_ids)
    
    # Process chunks
    while True:
        # Check progress
        progress = get_progress(processed_count, total_chunks)
        logger.info(f"Progress: {progress['processed_chunks']}/{progress['total_chunks']} "
                   f"chunks ({progress['percentage']}%)")
        
        # Check if target reached
        if progress["percentage"] >= target_percentage:
            logger.info(f"Target percentage {target_percentage}% reached, stopping")
            break
        
        # Check if max chunks reached
        if max_chunks is not None and stats["chunks_processed"] >= max_chunks:
            logger.info(f"Maximum chunks {max_chunks} processed, stopping")
            break
        
        # Get next chunk
        chunk = get_next_chunk(processed_ids)
        
        # If no more chunks, stop
        if not chunk:
            logger.info("No more chunks to process, stopping")
            break
        
        # Process chunk
        success = process_chunk(chunk, document_data, index)
        
        # Update stats
        stats["chunks_processed"] += 1
        
        if success:
            chunk_id = chunk["chunk_id"]
            processed_ids.add(chunk_id)
            processed_count += 1
            stats["successful"] += 1
            
            # Save after each successful chunk
            save_vector_store(document_data, index)
            save_checkpoint(processed_ids)
        else:
            stats["failed"] += 1
        
        # Delay between chunks
        if delay_seconds > 0:
            time.sleep(delay_seconds)
    
    # Print final stats
    end_time = datetime.datetime.now()
    duration = (end_time - stats["start_time"]).total_seconds()
    logger.info(f"Processing completed in {duration:.2f} seconds")
    logger.info(f"Chunks processed: {stats['chunks_processed']}")
    logger.info(f"Successful: {stats['successful']}")
    logger.info(f"Failed: {stats['failed']}")
    
    # Final progress
    progress = get_progress(processed_count, total_chunks)
    logger.info(f"Final progress: {progress['processed_chunks']}/{progress['total_chunks']} "
               f"chunks ({progress['percentage']}%)")

# Main function
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Simple chunk processor for vector store")
    parser.add_argument("--target", type=float, default=40.0,
                      help="Target percentage of completion")
    parser.add_argument("--max-chunks", type=int, default=None,
                      help="Maximum number of chunks to process")
    parser.add_argument("--delay", type=int, default=3,
                      help="Delay in seconds between processing chunks")
    
    args = parser.parse_args()
    
    try:
        run_processor(
            target_percentage=args.target,
            max_chunks=args.max_chunks,
            delay_seconds=args.delay
        )
    except KeyboardInterrupt:
        logger.info("Processor interrupted by user")
    except Exception as e:
        logger.error(f"Processor failed with error: {e}")
        sys.exit(1)