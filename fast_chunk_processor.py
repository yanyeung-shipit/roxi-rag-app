#!/usr/bin/env python3
"""
Fast Chunk Processor

This script processes a single chunk very quickly to add it to the vector store.
It's designed to be as fast as possible while still being reliable.

Usage:
    python fast_chunk_processor.py [chunk_id]
    
If no chunk_id is provided, it will automatically find the next chunk to process.
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime

from app import app, db
from models import Document, DocumentChunk
from utils.vector_store import VectorStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Initialize vector store
vector_store = VectorStore()

def get_next_chunk_id():
    """
    Find the next chunk ID that needs to be processed.
    
    Returns:
        int: The next chunk ID to process, or None if all are processed
    """
    with app.app_context():
        # Get all chunks from database
        all_chunks = DocumentChunk.query.order_by(DocumentChunk.id).all()
        all_chunk_ids = set(chunk.id for chunk in all_chunks)
        
        # Get processed chunks from vector store
        processed_chunk_ids = set()
        for doc in vector_store.documents:
            if isinstance(doc, dict):
                metadata = doc.get("metadata", {})
                chunk_id = metadata.get("chunk_id")
                if chunk_id:
                    processed_chunk_ids.add(int(chunk_id))
            elif hasattr(doc, "metadata") and isinstance(doc.metadata, dict):
                chunk_id = doc.metadata.get("chunk_id")
                if chunk_id:
                    processed_chunk_ids.add(int(chunk_id))
        
        # Find unprocessed chunks
        unprocessed_chunk_ids = all_chunk_ids - processed_chunk_ids
        
        if not unprocessed_chunk_ids:
            return None
            
        return min(unprocessed_chunk_ids)

def process_chunk(chunk_id):
    """
    Process a single chunk and add it to the vector store.
    
    Args:
        chunk_id: ID of the chunk to process
        
    Returns:
        bool: True if successful, False otherwise
    """
    with app.app_context():
        try:
            # Get the chunk from the database
            chunk = DocumentChunk.query.get(chunk_id)
            if not chunk:
                logger.error(f"Chunk {chunk_id} not found in database")
                return False
            
            # Get the document the chunk belongs to
            document = Document.query.get(chunk.document_id)
            if not document:
                logger.error(f"Document {chunk.document_id} not found for chunk {chunk_id}")
                return False
            
            logger.info(f"Processing chunk {chunk_id} from document {chunk.document_id}: {document.filename}")
            
            # Extract text and metadata
            text = chunk.text_content
            metadata = {
                "chunk_id": chunk.id,
                "document_id": document.id,
                "filename": document.filename,
                "page_number": chunk.page_number,
                "chunk_index": chunk.chunk_index,
                "doi": document.doi,
                "authors": document.authors,
                "journal": document.journal,
                "publication_year": document.publication_year,
                "formatted_citation": document.formatted_citation
            }
            
            # Add to vector store using add_text method
            vector_store.add_text(text, metadata=metadata)
            # The vector store saves automatically periodically, but we'll save just to be sure
            vector_store.save()
            
            return True
        except Exception as e:
            logger.error(f"Error processing chunk {chunk_id}: {e}")
            return False

def main():
    """Main function to process a single chunk"""
    parser = argparse.ArgumentParser(description="Process a single chunk to add to vector store")
    parser.add_argument("chunk_id", type=int, nargs='?', default=None, 
                      help="ID of the chunk to process (optional)")
    args = parser.parse_args()
    
    # Get the chunk ID to process
    chunk_id = args.chunk_id
    if chunk_id is None:
        chunk_id = get_next_chunk_id()
        if chunk_id is None:
            logger.info("No more chunks to process!")
            return
    
    # Process the chunk
    logger.info(f"Processing chunk {chunk_id}")
    start_time = time.time()
    success = process_chunk(chunk_id)
    elapsed_time = time.time() - start_time
    
    # Report results
    if success:
        logger.info(f"Successfully processed chunk {chunk_id} in {elapsed_time:.2f} seconds")
    else:
        logger.error(f"Failed to process chunk {chunk_id}")
    
    # Get vector store stats
    vector_count = len(vector_store.documents)
    logger.info(f"Vector store now contains {vector_count} documents")

if __name__ == "__main__":
    main()