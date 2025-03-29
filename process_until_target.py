#!/usr/bin/env python3
"""
Process chunks until a target percentage is reached.
This script processes individual chunks in sequence with timeout protection.

Usage:
    python process_until_target.py --start-chunk=CHUNK_ID --target-percentage=50.0 --max-chunks=10
"""

import argparse
import concurrent.futures
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple, Union

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"logs/sequential_processing/target_processing_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    ]
)
logger = logging.getLogger(__name__)

# Ensure log directory exists
os.makedirs("logs/sequential_processing", exist_ok=True)

def get_current_progress() -> Dict[str, Union[int, float, str]]:
    """
    Get the current progress of the vector store rebuild.
    
    Returns:
        dict: Dictionary with progress information
    """
    try:
        from app import app as flask_app
        from models import db, DocumentChunk
        from utils.vector_store import VectorStore
        from sqlalchemy import func
        
        with flask_app.app_context():
            # Get vector store stats
            vector_store = VectorStore()
            vector_count = len(vector_store.documents)
            
            # Get database stats
            total_chunks = db.session.query(func.count(DocumentChunk.id)).scalar()
            
            # Calculate progress
            if total_chunks > 0:
                percentage = round(vector_count / total_chunks * 100, 1)
            else:
                percentage = 0.0
                
            remaining = total_chunks - vector_count
            
            # Estimated time (assuming 3 seconds per chunk)
            est_seconds = remaining * 3
            est_minutes = est_seconds // 60
            est_hours = est_minutes // 60
            est_minutes %= 60
            
            return {
                "vector_count": vector_count,
                "total_chunks": total_chunks,
                "percentage": percentage,
                "remaining": remaining,
                "est_time": f"{est_hours}h {est_minutes}m"
            }
    except Exception as e:
        logger.error(f"Error getting progress: {e}")
        return {
            "vector_count": 0,
            "total_chunks": 0,
            "percentage": 0.0,
            "remaining": 0,
            "est_time": "unknown",
            "error": str(e)
        }

def process_chunk(chunk_id: int, timeout: int = 90) -> Dict[str, Union[bool, str, int]]:
    """
    Process a single chunk with timeout protection.
    
    Args:
        chunk_id (int): ID of the chunk to process
        timeout (int): Timeout in seconds
        
    Returns:
        dict: Processing result
    """
    def _process_chunk():
        try:
            from app import app as flask_app
            from models import db, DocumentChunk
            from utils.vector_store import VectorStore
            from openai import OpenAI
            
            with flask_app.app_context():
                # Get the chunk
                chunk = db.session.get(DocumentChunk, chunk_id)
                
                if not chunk:
                    return {
                        "success": False,
                        "chunk_id": chunk_id,
                        "error": "Chunk not found"
                    }
                
                # Get document for metadata
                document = chunk.document
                
                # Initialize vector store
                vector_store = VectorStore()
                
                # Create embedding service using OpenAI directly
                client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
                
                # Generate embedding
                response = client.embeddings.create(
                    input=chunk.text_content,
                    model="text-embedding-ada-002"
                )
                embedding = response.data[0].embedding
                
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
                vector_store.add_embedding(
                    text=chunk.text_content,
                    metadata=metadata,
                    embedding=embedding
                )
                vector_store.save()
                
                return {
                    "success": True,
                    "chunk_id": chunk_id,
                    "document_id": chunk.document_id,
                    "document_title": document.title or document.filename
                }
                
        except Exception as e:
            logger.error(f"Error processing chunk {chunk_id}: {e}")
            return {
                "success": False,
                "chunk_id": chunk_id,
                "error": str(e)
            }
    
    # Use ThreadPoolExecutor with timeout
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_process_chunk)
            result = future.result(timeout=timeout)
            return result
    except concurrent.futures.TimeoutError:
        logger.error(f"Timeout processing chunk {chunk_id}")
        return {
            "success": False,
            "chunk_id": chunk_id,
            "error": f"Processing timed out after {timeout} seconds"
        }

def process_until_target(start_chunk: int = 1, 
                         target_percentage: float = 50.0,
                         max_chunks: int = 10,
                         chunk_timeout: int = 90) -> Dict[str, Union[int, float, bool, str]]:
    """
    Process chunks until target percentage is reached or max chunks processed.
    
    Args:
        start_chunk (int): ID of the chunk to start with
        target_percentage (float): Target percentage to reach
        max_chunks (int): Maximum number of chunks to process
        chunk_timeout (int): Timeout in seconds for each chunk
        
    Returns:
        dict: Processing results
    """
    logger.info(f"Starting chunk processing from chunk {start_chunk}")
    logger.info(f"Target: {target_percentage}%, Max chunks: {max_chunks}")
    
    # Get initial progress
    initial_progress = get_current_progress()
    logger.info(f"Initial progress: {initial_progress['percentage']}%")
    
    chunks_processed = 0
    successful_chunks = 0
    current_chunk_id = start_chunk
    
    start_time = time.time()
    
    while chunks_processed < max_chunks:
        # Check if we've reached the target percentage
        if target_percentage > 0:
            current_progress = get_current_progress()
            logger.info(f"Current progress: {current_progress['percentage']}% (Target: {target_percentage}%)")
            
            if current_progress["percentage"] >= target_percentage:
                logger.info(f"Target percentage reached: {current_progress['percentage']}%")
                break
        
        logger.info(f"Processing chunk {current_chunk_id} ({chunks_processed + 1} of {max_chunks})...")
        
        # Process the chunk with timeout protection
        result = process_chunk(current_chunk_id, timeout=chunk_timeout)
        
        if result["success"]:
            logger.info(f"✓ Successfully processed chunk {current_chunk_id}")
            successful_chunks += 1
        else:
            logger.error(f"✗ Failed to process chunk {current_chunk_id}: {result.get('error', 'Unknown error')}")
        
        chunks_processed += 1
        current_chunk_id += 1
        
        # Add a short delay to prevent rate limiting
        time.sleep(1)
    
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    # Get final progress
    final_progress = get_current_progress()
    
    result = {
        "initial_percentage": initial_progress["percentage"],
        "final_percentage": final_progress["percentage"],
        "chunks_processed": chunks_processed,
        "successful_chunks": successful_chunks,
        "failed_chunks": chunks_processed - successful_chunks,
        "elapsed_seconds": elapsed_time,
        "reached_target": final_progress["percentage"] >= target_percentage,
        "target_percentage": target_percentage
    }
    
    logger.info("=" * 60)
    logger.info("PROCESSING COMPLETE")
    logger.info(f"Chunks processed: {chunks_processed} (Successful: {successful_chunks}, Failed: {chunks_processed - successful_chunks})")
    logger.info(f"Progress: {initial_progress['percentage']}% → {final_progress['percentage']}%")
    logger.info(f"Time taken: {elapsed_time:.1f} seconds")
    logger.info("=" * 60)
    
    return result

def main():
    """Main function to parse arguments and run the processor."""
    parser = argparse.ArgumentParser(description="Process chunks until target percentage is reached")
    parser.add_argument("--start-chunk", type=int, default=1, help="Chunk ID to start with")
    parser.add_argument("--target-percentage", type=float, default=50.0, help="Target percentage to reach")
    parser.add_argument("--max-chunks", type=int, default=10, help="Maximum number of chunks to process")
    parser.add_argument("--chunk-timeout", type=int, default=90, help="Timeout in seconds for each chunk")
    
    args = parser.parse_args()
    
    result = process_until_target(
        start_chunk=args.start_chunk,
        target_percentage=args.target_percentage,
        max_chunks=args.max_chunks,
        chunk_timeout=args.chunk_timeout
    )
    
    # Output final result as JSON
    print(json.dumps(result, indent=2))
    
    return 0 if result["reached_target"] or result["successful_chunks"] > 0 else 1

if __name__ == "__main__":
    sys.exit(main())