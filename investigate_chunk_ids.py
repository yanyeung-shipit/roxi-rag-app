"""
Script to investigate the chunk_id issue in vector store documents.
This analyzes why so many documents don't have proper chunk_ids.
"""

import os
import pickle
import sys
import logging
from collections import Counter
from typing import Dict, List, Any, Set, Optional
import json

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Path to the vector store data
VECTOR_STORE_PATH = 'document_data.pkl'

def load_vector_store() -> Dict[str, Any]:
    """Load the vector store data from disk."""
    if not os.path.exists(VECTOR_STORE_PATH):
        logger.error(f"Vector store data not found at {VECTOR_STORE_PATH}")
        sys.exit(1)
        
    try:
        with open(VECTOR_STORE_PATH, 'rb') as f:
            data = pickle.load(f)
        return data
    except Exception as e:
        logger.error(f"Error loading vector store: {e}")
        sys.exit(1)

def analyze_chunk_ids():
    """Analyze the chunk_id issue in vector store documents."""
    logger.info(f"Loading vector store data from {VECTOR_STORE_PATH}")
    data = load_vector_store()
    
    # Extract documents
    documents = data.get('documents', {})
    logger.info(f"Vector store has {len(documents)} total documents")
    
    # Count metadata fields
    metadata_fields_counter = Counter()
    has_chunk_id = 0
    has_db_chunk_id = 0
    has_chunk_index = 0
    has_source_type = 0
    source_types = Counter()
    
    # Sample documents with and without chunk_id
    sample_with_chunk_id = None
    sample_without_chunk_id = None
    
    # Collect all metadata fields
    all_metadata_fields = set()
    
    for doc_id, doc in documents.items():
        metadata = doc.get('metadata', {})
        
        # Count all metadata fields present
        for field in metadata:
            metadata_fields_counter[field] += 1
            all_metadata_fields.add(field)
        
        # Check for specific fields
        if 'chunk_id' in metadata:
            has_chunk_id += 1
            if sample_with_chunk_id is None:
                sample_with_chunk_id = (doc_id, doc)
        else:
            if sample_without_chunk_id is None:
                sample_without_chunk_id = (doc_id, doc)
                
        if 'db_chunk_id' in metadata:
            has_db_chunk_id += 1
            
        if 'chunk_index' in metadata:
            has_chunk_index += 1
            
        if 'source_type' in metadata:
            has_source_type += 1
            source_type = metadata.get('source_type', 'unknown')
            source_types[source_type] += 1
    
    # Log statistics
    logger.info(f"Documents with chunk_id: {has_chunk_id} ({has_chunk_id/len(documents)*100:.2f}%)")
    logger.info(f"Documents with db_chunk_id: {has_db_chunk_id} ({has_db_chunk_id/len(documents)*100:.2f}%)")
    logger.info(f"Documents with chunk_index: {has_chunk_index} ({has_chunk_index/len(documents)*100:.2f}%)")
    logger.info(f"Documents with source_type: {has_source_type} ({has_source_type/len(documents)*100:.2f}%)")
    
    logger.info("\nSource type distribution:")
    for source_type, count in source_types.most_common():
        logger.info(f"  {source_type}: {count} ({count/len(documents)*100:.2f}%)")
    
    logger.info("\nMetadata fields distribution:")
    for field, count in metadata_fields_counter.most_common():
        logger.info(f"  {field}: {count} ({count/len(documents)*100:.2f}%)")
    
    logger.info("\nAll metadata fields found:")
    logger.info(f"  {sorted(all_metadata_fields)}")
    
    # Log sample documents
    if sample_with_chunk_id:
        doc_id, doc = sample_with_chunk_id
        logger.info("\nSample document WITH chunk_id:")
        logger.info(f"  ID: {doc_id}")
        logger.info(f"  Metadata: {json.dumps(doc.get('metadata', {}), indent=2)}")
        
    if sample_without_chunk_id:
        doc_id, doc = sample_without_chunk_id
        logger.info("\nSample document WITHOUT chunk_id:")
        logger.info(f"  ID: {doc_id}")
        logger.info(f"  Metadata: {json.dumps(doc.get('metadata', {}), indent=2)}")

def main():
    analyze_chunk_ids()

if __name__ == "__main__":
    main()