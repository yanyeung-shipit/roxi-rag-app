#!/usr/bin/env python3
"""
Parallel Chunk Processor

Process multiple chunks at once with optimal resource utilization.
This script is designed to efficiently process chunks in batches to
maximize throughput while avoiding Replit resource limits.
"""

import os
import sys
import time
import logging
import json
import argparse
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Set, Union, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

# Set OpenAI API key early to avoid repetitive logging
os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "")

# Import app and models
from app import app as flask_app
from models import db, DocumentChunk
from utils.vector_store import VectorStore
from openai import OpenAI

# Simple embedding service that minimizes overhead
class EmbeddingService:
    """Optimized embedding service with caching."""
    
    def __init__(self):
        """Initialize the service."""
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.model = "text-embedding-ada-002"
        self.cache = {}  # Simple in-memory cache
    
    def get_embedding(self, text: str) -> List[float]:
        """Get embedding for text with caching."""
        # Use a hash of the text as a cache key
        cache_key = hash(text)
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # Generate embedding
        response = self.client.embeddings.create(
            input=text,
            model=self.model
        )
        embedding = response.data[0].embedding
        
        # Cache the result
        self.cache[cache_key] = embedding
        return embedding

def get_unprocessed_chunks(limit: int = 10) -> List[int]:
    """
    Get a list of chunk IDs that need to be processed.
    
    Args:
        limit: Maximum number of chunks to retrieve
        
    Returns:
        List of chunk IDs
    """
    with flask_app.app_context():
        # Get all chunks from the database
        chunks = db.session.query(DocumentChunk.id).order_by(DocumentChunk.id).all()
        chunk_ids = [chunk[0] for chunk in chunks]
        
        # Get chunks that are already in the vector store
        vector_store = VectorStore()
        processed_ids = set()
        for doc in vector_store.documents:
            if "chunk_id" in doc.metadata:
                processed_ids.add(doc.metadata["chunk_id"])
        
        # Find chunks that haven't been processed yet
        unprocessed_ids = [cid for cid in chunk_ids if cid not in processed_ids]
        
        return unprocessed_ids[:limit]

def process_chunk(chunk_id: int) -> Dict[str, Any]:
    """
    Process a single chunk and add it to the vector store.
    
    Args:
        chunk_id: ID of the chunk to process
        
    Returns:
        Dictionary with processing results
    """
    start_time = time.time()
    result = {
        "chunk_id": chunk_id,
        "success": False,
        "time_taken": 0,
        "error": None
    }
    
    try:
        with flask_app.app_context():
            # Get the chunk
            chunk = db.session.get(DocumentChunk, chunk_id)
            if not chunk:
                result["error"] = f"Chunk {chunk_id} not found"
                return result
            
            # Get document for metadata
            document = chunk.document
            
            # Generate embedding
            embedding_service = EmbeddingService()
            embedding = embedding_service.get_embedding(chunk.text_content)
            
            # Create metadata
            metadata = {
                "document_id": chunk.document_id,
                "chunk_id": chunk_id,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number,
                "source_type": document.file_type,
                "filename": document.filename,
                "title": document.title or document.filename
            }
            
            # Add citation if available
            if document.formatted_citation:
                metadata["formatted_citation"] = document.formatted_citation
                metadata["citation"] = document.formatted_citation
            
            if document.doi:
                metadata["doi"] = document.doi
            
            if document.source_url:
                metadata["url"] = document.source_url
            
            # Add to vector store
            vector_store = VectorStore()
            vector_store.add_embedding(
                text=chunk.text_content,
                metadata=metadata,
                embedding=embedding
            )
            vector_store.save()
            
            result["success"] = True
    except Exception as e:
        result["error"] = str(e)
    
    # Calculate time taken
    result["time_taken"] = time.time() - start_time
    return result

def process_chunks_batch(chunk_ids: List[int], max_workers: int = 3) -> List[Dict[str, Any]]:
    """
    Process a batch of chunks in parallel.
    
    Args:
        chunk_ids: List of chunk IDs to process
        max_workers: Maximum number of parallel workers
        
    Returns:
        List of processing results
    """
    results = []
    
    # Process chunks in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_chunk, chunk_id) for chunk_id in chunk_ids]
        for future in futures:
            results.append(future.result())
    
    return results

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Process chunks in parallel")
    parser.add_argument("--limit", type=int, default=5, help="Number of chunks to process")
    parser.add_argument("--workers", type=int, default=3, help="Maximum number of parallel workers")
    parser.add_argument("--input", type=str, help="Optional input file with chunk IDs (JSON)")
    args = parser.parse_args()
    
    # Get initial vector store size
    with flask_app.app_context():
        vector_store = VectorStore()
        initial_count = len(vector_store.documents)
    
    # Get chunk IDs to process
    if args.input and os.path.exists(args.input):
        with open(args.input, 'r') as f:
            chunk_ids = json.load(f)
    else:
        chunk_ids = get_unprocessed_chunks(args.limit)
    
    if not chunk_ids:
        print("No unprocessed chunks found.")
        return
    
    print(f"Processing {len(chunk_ids)} chunks with {args.workers} workers...")
    
    # Process chunks
    start_time = time.time()
    results = process_chunks_batch(chunk_ids, args.workers)
    
    # Print results
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    
    print("\nPROCESSING RESULTS:")
    print(f"Total chunks:      {len(chunk_ids)}")
    print(f"Successful:        {len(successful)}")
    print(f"Failed:            {len(failed)}")
    print(f"Time taken:        {time.time() - start_time:.2f} seconds")
    
    # Get final vector store size
    with flask_app.app_context():
        vector_store = VectorStore()
        final_count = len(vector_store.documents)
    
    print(f"Documents added:   {final_count - initial_count}")
    print(f"Vector store size: {final_count} documents")
    
    # Print failed chunks if any
    if failed:
        print("\nFAILED CHUNKS:")
        for fail in failed:
            print(f"  - Chunk {fail['chunk_id']}: {fail['error']}")

if __name__ == "__main__":
    main()