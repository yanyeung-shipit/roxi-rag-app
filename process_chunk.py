#!/usr/bin/env python3
"""
Process a single chunk by ID and add it to the vector store.
This script takes a chunk ID as an argument and processes just that chunk.

Usage:
    python process_chunk.py CHUNK_ID
"""

import argparse
import sys
import logging
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
            
            # Add to vector store
            vector_store = VectorStore()
            vector_store.add_text(text, metadata=metadata)
            vector_store.save()
            
            return True
        except Exception as e:
            logger.error(f"Error processing chunk {chunk_id}: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description="Process a specific chunk and add it to the vector store")
    parser.add_argument("chunk_id", type=int, help="ID of the chunk to process")
    args = parser.parse_args()
    
    start_time = time.time()
    success = process_chunk(args.chunk_id)
    elapsed_time = time.time() - start_time
    
    if success:
        logger.info(f"Successfully processed chunk {args.chunk_id} in {elapsed_time:.2f} seconds")
        sys.exit(0)
    else:
        logger.error(f"Failed to process chunk {args.chunk_id}")
        sys.exit(1)

if __name__ == "__main__":
    main()