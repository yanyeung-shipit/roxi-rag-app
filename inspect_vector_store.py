#!/usr/bin/env python3
"""
Inspect the structure of the vector store documents.
"""

import os
import sys
import logging
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the current directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.vector_store import VectorStore

def inspect_vector_store():
    """Inspect the structure of vector store documents."""
    # Initialize vector store
    vector_store = VectorStore()
    
    # Get total count
    documents = vector_store.documents
    total_docs = len(documents)
    logger.info(f"Total documents in vector store: {total_docs}")
    logger.info(f"Document type: {type(documents)}")
    
    # Examine the documents object
    if hasattr(documents, 'items'):
        logger.info("Documents object has 'items' method (likely a dictionary)")
        # Grab a few keys to inspect
        some_keys = list(documents.keys())[:5]
        logger.info(f"Sample keys: {some_keys}")
        
        # Look at a few values
        for key in some_keys:
            logger.info(f"Document with key {key}:")
            doc = documents[key]
            logger.info(f"  Type: {type(doc)}")
            
            # Try to access content and metadata
            try:
                if hasattr(doc, 'page_content'):
                    logger.info(f"  Page content (excerpt): {doc.page_content[:50]}...")
                else:
                    logger.info("  No page_content attribute")
                    
                if hasattr(doc, 'metadata'):
                    logger.info(f"  Metadata type: {type(doc.metadata)}")
                    if isinstance(doc.metadata, dict):
                        logger.info(f"  Metadata keys: {list(doc.metadata.keys())}")
                    else:
                        logger.info(f"  Metadata: {doc.metadata}")
                else:
                    logger.info("  No metadata attribute")
                
                # Check if it's a dictionary
                if isinstance(doc, dict):
                    logger.info(f"  Dictionary keys: {list(doc.keys())}")
                    if 'metadata' in doc:
                        logger.info(f"  doc['metadata'] type: {type(doc['metadata'])}")
                        if isinstance(doc['metadata'], dict):
                            logger.info(f"  doc['metadata'] keys: {list(doc['metadata'].keys())}")
                        else:
                            logger.info(f"  doc['metadata']: {doc['metadata']}")
                
                logger.info(f"  Raw representation: {repr(doc)[:200]}...")
            except Exception as e:
                logger.error(f"  Error inspecting document: {str(e)}")
            
            logger.info("---")
    elif isinstance(documents, list):
        logger.info("Documents object is a list")
        for i, doc in enumerate(documents[:5]):
            logger.info(f"Document {i}:")
            logger.info(f"  Type: {type(doc)}")
            # Rest of inspection code...
    else:
        logger.info(f"Documents object is neither a dict nor a list: {type(documents)}")
    
    # Count documents with various ID fields
    chunk_id_count = 0
    db_id_count = 0
    chunk_index_count = 0
    documents = vector_store.documents
    
    if hasattr(documents, 'items'):
        # It's a dictionary-like object
        for key, doc in documents.items():
            try:
                # Check for chunk_id
                if hasattr(doc, 'metadata') and isinstance(doc.metadata, dict) and 'chunk_id' in doc.metadata:
                    chunk_id_count += 1
                elif isinstance(doc, dict) and 'metadata' in doc and isinstance(doc['metadata'], dict) and 'chunk_id' in doc['metadata']:
                    chunk_id_count += 1
                
                # Check for db_id
                if isinstance(doc, dict) and 'metadata' in doc and isinstance(doc['metadata'], dict) and 'db_id' in doc['metadata']:
                    db_id_count += 1
                    # Sample some db_id values
                    if db_id_count <= 5:
                        logger.info(f"  Sample db_id: {doc['metadata']['db_id']}")
                
                # Check for chunk_index
                if isinstance(doc, dict) and 'metadata' in doc and isinstance(doc['metadata'], dict) and 'chunk_index' in doc['metadata']:
                    chunk_index_count += 1
                    # Sample some chunk_index values
                    if chunk_index_count <= 5:
                        logger.info(f"  Sample chunk_index: {doc['metadata']['chunk_index']}")
                
            except Exception as e:
                logger.error(f"Error inspecting document {key}: {str(e)}")
    
    logger.info(f"Documents with chunk_id in metadata: {chunk_id_count} / {total_docs}")
    logger.info(f"Documents with db_id in metadata: {db_id_count} / {total_docs}")
    logger.info(f"Documents with chunk_index in metadata: {chunk_index_count} / {total_docs}")

if __name__ == "__main__":
    inspect_vector_store()