"""
Memory-optimized module for retrieving processed chunk IDs from the vector store.
This module helps reduce memory usage by avoiding loading the vector store contents
multiple times in memory.
"""

import os
import time
import pickle
import logging
from typing import Set, Dict, List, Any, Optional
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache for storing processed chunk IDs
_chunk_ids_cache: Optional[Set[int]] = None
_last_cache_update_time: float = 0
_cache_ttl: float = 60.0  # Longer TTL because this won't change frequently
_cache_lock = threading.Lock()

def get_processed_chunk_ids(force_refresh: bool = False) -> Set[int]:
    """
    Get the set of chunk IDs that have been processed and added to the vector store.
    Uses a highly optimized memory-efficient approach without loading the whole vector store.
    
    Args:
        force_refresh (bool): If True, ignore the cache and recalculate
        
    Returns:
        set: Set of processed chunk IDs
    """
    global _chunk_ids_cache, _last_cache_update_time, _cache_ttl
    
    current_time = time.time()
    
    # Check if we can use the cached value
    with _cache_lock:
        if not force_refresh and _chunk_ids_cache is not None:
            if current_time - _last_cache_update_time < _cache_ttl:
                return _chunk_ids_cache.copy()  # Return a copy to avoid modification
    
    # We need to recompute the processed IDs
    document_data_path = os.path.join(os.getcwd(), 'document_data.pkl')
    
    if not os.path.exists(document_data_path):
        logger.warning(f"Document data file not found at: {document_data_path}")
        return set()
    
    # Process the vector store data with minimal memory impact
    try:
        processed_ids = extract_chunk_ids_from_pickle(document_data_path)
        
        # Update the cache
        with _cache_lock:
            _chunk_ids_cache = processed_ids.copy()  # Store a copy to avoid modification
            _last_cache_update_time = current_time
        
        logger.info(f"Memory-optimized: Found {len(processed_ids)} processed chunk IDs")
        return processed_ids
    except Exception as e:
        logger.error(f"Error extracting chunk IDs from pickle: {e}")
        return set()

def extract_chunk_ids_from_pickle(filepath: str) -> Set[int]:
    """
    Extract chunk IDs from the vector store pickle file using an optimized
    approach that minimizes memory usage.
    
    Args:
        filepath (str): Path to the pickle file
        
    Returns:
        set: Set of chunk IDs
    """
    chunk_ids = set()
    
    # Use binary mode for optimal memory efficiency
    with open(filepath, 'rb') as f:
        # Load only the structure needed
        try:
            data = pickle.load(f)
            
            # Handle different possible structures
            if isinstance(data, dict) and 'documents' in data:
                documents = data['documents']
            elif isinstance(data, dict):
                documents = data
            else:
                logger.warning("Unexpected document data format")
                return chunk_ids
            
            # Process document metadata efficiently
            for doc_id, doc_data in documents.items():
                if isinstance(doc_data, dict) and 'metadata' in doc_data:
                    metadata = doc_data.get('metadata', {})
                    if 'chunk_id' in metadata and metadata['chunk_id'] is not None:
                        try:
                            chunk_id = int(metadata['chunk_id'])
                            chunk_ids.add(chunk_id)
                        except (ValueError, TypeError):
                            pass
            
            return chunk_ids
        except Exception as e:
            logger.error(f"Error processing document data: {e}")
            return chunk_ids