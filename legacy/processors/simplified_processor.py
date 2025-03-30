#!/usr/bin/env python
"""
Super simplified processor for adding documents to vector store.
This is designed to be as reliable as possible in Replit's environment.
"""

import os
import time
import sys
import json
import pickle
import logging
import datetime
from typing import Dict, Any, Set, List, Optional, Tuple

import faiss
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor
import openai

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Constants
DB_URL = os.environ.get("DATABASE_URL")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
EMBEDDING_MODEL = "text-embedding-ada-002"
VECTOR_DATA_FILE = "document_data.pkl"
FAISS_INDEX_FILE = "faiss_index.bin"
CHECKPOINT_FILE = "processor_checkpoint.json"
DEFAULT_DELAY = 3

# Initialize OpenAI client
openai.api_key = OPENAI_API_KEY

# Process a single chunk and update vector store
def process_next_chunk():
    """Process a single chunk and update the vector store."""
    try:
        # Connect to database
        conn = psycopg2.connect(DB_URL)
        
        # Get total count
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM document_chunks")
            total_count = cur.fetchone()[0]
        
        # Get a list of processed chunk IDs
        processed_ids = set()
        if os.path.exists(VECTOR_DATA_FILE):
            with open(VECTOR_DATA_FILE, 'rb') as f:
                document_data = pickle.load(f)
                
            # Ensure all required keys exist
            if not isinstance(document_data, dict):
                document_data = {}
            if "documents" not in document_data:
                document_data["documents"] = {}
            if "id_to_uuid" not in document_data:
                document_data["id_to_uuid"] = {}
            if "next_id" not in document_data:
                document_data["next_id"] = 0
            
            # Extract processed chunk IDs
            for doc_id, doc in document_data.get("documents", {}).items():
                if "chunk_id" in doc:
                    processed_ids.add(doc["chunk_id"])
                elif "metadata" in doc and "chunk_id" in doc["metadata"]:
                    processed_ids.add(doc["metadata"]["chunk_id"])
        else:
            # Create empty document data
            document_data = {"documents": {}, "id_to_uuid": {}, "next_id": 0}
        
        processed_count = len(processed_ids)
        
        # Log progress
        percentage = (processed_count / total_count * 100) if total_count > 0 else 0
        logger.info(f"Progress: {processed_count}/{total_count} chunks ({percentage:.2f}%)")
        
        # Check if we've already reached 40%
        if percentage >= 40:
            logger.info("Target percentage of 40% already reached, stopping")
            return False
        
        # Get next unprocessed chunk
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Simple query to get one unprocessed chunk
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
        
        # Close database connection
        conn.close()
        
        if not chunk:
            logger.info("No more chunks to process, stopping")
            return False
        
        # Get embedding
        chunk_id = chunk["chunk_id"]
        document_id = chunk["document_id"]
        content = chunk["content"]
        
        logger.info(f"Processing chunk {chunk_id} from document {document_id}")
        
        # Get embedding from OpenAI
        response = openai.embeddings.create(
            model=EMBEDDING_MODEL,
            input=content
        )
        embedding = response.data[0].embedding
        
        # Load or create FAISS index
        if os.path.exists(FAISS_INDEX_FILE):
            index = faiss.read_index(FAISS_INDEX_FILE)
        else:
            dimension = 1536  # OpenAI embedding dimension
            index = faiss.IndexFlatL2(dimension)
        
        # Add chunk to vector store
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
        
        # Create backups before saving
        if os.path.exists(VECTOR_DATA_FILE):
            backup_name = f"{VECTOR_DATA_FILE}.bak.{int(time.time())}"
            os.rename(VECTOR_DATA_FILE, backup_name)
        
        if os.path.exists(FAISS_INDEX_FILE):
            backup_name = f"{FAISS_INDEX_FILE}.bak.{int(time.time())}"
            os.rename(FAISS_INDEX_FILE, backup_name)
        
        # Save vector store
        with open(VECTOR_DATA_FILE, 'wb') as f:
            pickle.dump(document_data, f)
        
        faiss.write_index(index, FAISS_INDEX_FILE)
        
        logger.info(f"Successfully processed chunk {chunk_id} from document {document_id}")
        
        # Update progress
        processed_count += 1
        percentage = (processed_count / total_count * 100) if total_count > 0 else 0
        logger.info(f"New progress: {processed_count}/{total_count} chunks ({percentage:.2f}%)")
        
        # Save checkpoint
        with open(CHECKPOINT_FILE, 'w') as f:
            json.dump({
                "processed_ids": list(processed_ids) + [chunk_id],
                "timestamp": datetime.datetime.now().isoformat(),
                "last_chunk_id": chunk_id,
                "progress": {
                    "processed": processed_count,
                    "total": total_count,
                    "percentage": percentage
                }
            }, f)
        
        logger.info(f"Checkpoint saved with {processed_count} processed chunk IDs")
        
        return True
    except Exception as e:
        logger.error(f"Error processing chunk: {e}")
        return False

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Super simplified chunk processor")
    parser.add_argument("--delay", type=int, default=DEFAULT_DELAY,
                      help="Delay in seconds between processing chunks")
    
    args = parser.parse_args()
    
    try:
        logger.info(f"Starting simplified processor with {args.delay}s delay")
        
        while process_next_chunk():
            logger.info(f"Waiting {args.delay} seconds before next chunk...")
            time.sleep(args.delay)
            
        logger.info("Processing complete or target reached")
    except KeyboardInterrupt:
        logger.info("Processor interrupted by user")
    except Exception as e:
        logger.error(f"Processor failed with error: {e}")
        sys.exit(1)