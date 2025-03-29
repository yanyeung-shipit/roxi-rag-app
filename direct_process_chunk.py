#!/usr/bin/env python3
"""
Direct and simplified chunk processor - optimized for directly processing a specific chunk ID
without any overhead.
"""

import os
import sys
import time
import numpy as np
import logging
from typing import Dict, Any, List, Union, Optional, Tuple
from openai import OpenAI

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

# Import required modules
from app import app as flask_app
from models import db, DocumentChunk
from utils.vector_store import VectorStore

class SimpleEmbeddingService:
    """Simplified embedding service using OpenAI directly."""
    
    def __init__(self):
        """Initialize the embedding service."""
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.model = "text-embedding-ada-002"
    
    def get_embedding(self, text):
        """Generate embedding for text."""
        response = self.client.embeddings.create(
            input=text,
            model=self.model
        )
        return response.data[0].embedding

def process_chunk(chunk_id: int) -> bool:
    """Process a single chunk very efficiently."""
    start_time = time.time()
    
    with flask_app.app_context():
        # Get the chunk
        chunk = db.session.get(DocumentChunk, chunk_id)
        if not chunk:
            print(f"Chunk {chunk_id} not found")
            return False
        
        # Get document for metadata
        document = chunk.document
        
        # Initialize services
        vector_store = VectorStore()
        embedding_service = SimpleEmbeddingService()
        
        # Generate embedding
        try:
            embedding = embedding_service.get_embedding(chunk.text_content)
        except Exception as e:
            print(f"Embedding error: {e}")
            return False
        
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
        try:
            vector_store.add_embedding(
                text=chunk.text_content,
                metadata=metadata,
                embedding=embedding
            )
            vector_store.save()
            
            duration = time.time() - start_time
            print(f"✓ Processed chunk {chunk_id} in {duration:.2f}s")
            return True
        except Exception as e:
            print(f"Vector store error: {e}")
            return False

if __name__ == "__main__":
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