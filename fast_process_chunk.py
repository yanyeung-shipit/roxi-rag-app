#!/usr/bin/env python3
"""
Fast chunk processor optimized for speed.
Streamlined version of process_chunk.py that removes unnecessary logging.

Usage:
    python fast_process_chunk.py CHUNK_ID
"""

import os
import sys
import logging
import time
import numpy as np
from typing import Dict, Any, List, Union, Optional, Tuple

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

# Speed optimization: Import only what we need
from app import app as flask_app
from models import db, DocumentChunk
from utils.vector_store import VectorStore

# Define a simplified embedding service that uses the OpenAI API directly
import os
import openai
from openai import OpenAI

class OpenAIEmbeddingService:
    """Simplified embedding service that uses OpenAI directly."""
    
    def __init__(self):
        """Initialize the embedding service with OpenAI API key."""
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.model = "text-embedding-ada-002"
    
    def get_embedding(self, text):
        """Get embeddings for text using OpenAI API."""
        response = self.client.embeddings.create(
            input=text,
            model=self.model
        )
        return response.data[0].embedding

def get_chunk_by_id(chunk_id: int) -> Union[DocumentChunk, None]:
    """Get a chunk by its ID."""
    with flask_app.app_context():
        return db.session.get(DocumentChunk, chunk_id)

def process_chunk(chunk_id: int) -> bool:
    """
    Process a single chunk and add it to the vector store.
    
    Args:
        chunk_id: ID of the chunk to process
        
    Returns:
        bool: True if successful, False otherwise
    """
    start_time = time.time()
    
    # Load the chunk from the database
    chunk = get_chunk_by_id(chunk_id)
    if not chunk:
        logger.error(f"Chunk {chunk_id} not found in database")
        return False
    
    # Get document information
    document_id = chunk.document_id
    
    # Initialize vector store (directly)
    vector_store = VectorStore()
    
    # Initialize OpenAI embedding service
    embedding_service = OpenAIEmbeddingService()
    
    # Generate embedding for the chunk
    try:
        chunk_embedding = embedding_service.get_embedding(chunk.text_content)
    except Exception as e:
        logger.error(f"Failed to generate embedding for chunk {chunk_id}: {e}")
        return False
    
    # Get the document to extract more metadata
    with flask_app.app_context():
        # Get the document directly from the chunk's relationship
        document = chunk.document
        
        # Define comprehensive metadata
        metadata = {
            "document_id": document_id,
            "chunk_id": chunk_id,
            "chunk_index": chunk.chunk_index,
            "page_number": chunk.page_number,
            "source_type": document.file_type,
            "filename": document.filename,
            "title": document.title or document.filename
        }
        
        # Add citation information if available
        if document.formatted_citation:
            metadata["formatted_citation"] = document.formatted_citation
            metadata["citation"] = document.formatted_citation
        
        if document.doi:
            metadata["doi"] = document.doi
        
        if document.source_url:
            metadata["url"] = document.source_url
    
    # Add the chunk to the vector store
    try:
        vector_store.add_embedding(
            text=chunk.text_content,
            metadata=metadata,
            embedding=chunk_embedding
        )
        
        # Save the vector store
        vector_store.save()
        
        duration = time.time() - start_time
        logger.info(f"✅ Successfully processed chunk {chunk_id} in {duration:.2f}s")
        return True
    except Exception as e:
        logger.error(f"Failed to add chunk {chunk_id} to vector store: {e}")
        return False

def main():
    """Main function to process a single chunk."""
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} CHUNK_ID")
        sys.exit(1)
    
    try:
        chunk_id = int(sys.argv[1])
    except ValueError:
        print(f"Error: CHUNK_ID must be an integer, got '{sys.argv[1]}'")
        sys.exit(1)
    
    success = process_chunk(chunk_id)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()