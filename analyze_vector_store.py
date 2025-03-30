"""
Analyze the vector store structure to understand the document types and metadata.
"""

import os
import pickle
import logging
import json
from collections import Counter
from typing import Dict, Any, List, Set

# Configure logging
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
        return {"documents": {}, "document_counts": {}}
        
    try:
        with open(VECTOR_STORE_PATH, 'rb') as f:
            data = pickle.load(f)
        return data
    except Exception as e:
        logger.error(f"Error loading vector store: {e}")
        return {"documents": {}, "document_counts": {}}

def analyze_vector_store():
    """Analyze the vector store to understand its structure and content."""
    data = load_vector_store()
    documents = data.get('documents', {})
    document_counts = data.get('document_counts', {})
    
    logger.info(f"Vector store contains {len(documents)} documents")
    logger.info(f"Document counts by type: {dict(document_counts)}")
    
    # Analyze by source type
    source_types = Counter()
    # Count chunk IDs
    chunk_id_count = 0
    document_id_count = 0
    # Count unique document IDs
    unique_doc_ids = set()
    # Count documents by chunk index
    chunk_indices = Counter()
    
    # Count metadata fields
    metadata_fields = Counter()
    
    for doc_id, doc in documents.items():
        metadata = doc.get('metadata', {})
        
        # Source type
        source_type = metadata.get('source_type', 'unknown')
        source_types[source_type] += 1
        
        # Count documents with chunk_id field
        if 'chunk_id' in metadata:
            chunk_id_count += 1
        
        # Count documents with document_id field
        if 'document_id' in metadata:
            document_id_count += 1
            unique_doc_ids.add(metadata['document_id'])
        
        # Chunk index
        chunk_index = metadata.get('chunk_index', -1)
        chunk_indices[chunk_index] += 1
        
        # Count metadata fields
        for field in metadata:
            metadata_fields[field] += 1
    
    # Log results
    logger.info(f"Documents by source type:")
    for source_type, count in source_types.most_common():
        logger.info(f"  {source_type}: {count} ({count/len(documents)*100:.2f}%)")
    
    logger.info(f"Documents with chunk_id: {chunk_id_count} ({chunk_id_count/len(documents)*100:.2f}%)")
    logger.info(f"Documents with document_id: {document_id_count} ({document_id_count/len(documents)*100:.2f}%)")
    logger.info(f"Unique document IDs: {len(unique_doc_ids)}")
    
    logger.info(f"Chunk index distribution:")
    for index, count in sorted(chunk_indices.items())[:20]:  # Show first 20
        logger.info(f"  Index {index}: {count} documents")
    
    logger.info(f"Top metadata fields:")
    for field, count in metadata_fields.most_common():
        logger.info(f"  {field}: {count} ({count/len(documents)*100:.2f}%)")
    
    # Analyze document IDs to understand duplication
    analyze_document_ids(documents)
    
    # Analyze chunk IDs
    analyze_chunk_ids(documents)

def analyze_document_ids(documents: Dict[str, Any]):
    """Analyze document IDs to understand duplication."""
    # Map document_id to count of entries
    doc_id_counts = Counter()
    doc_id_to_entries = {}
    
    for entry_id, doc in documents.items():
        metadata = doc.get('metadata', {})
        if 'document_id' in metadata:
            doc_id = metadata['document_id']
            doc_id_counts[doc_id] += 1
            if doc_id not in doc_id_to_entries:
                doc_id_to_entries[doc_id] = []
            doc_id_to_entries[doc_id].append(entry_id)
    
    # Find documents with multiple entries
    duplicate_docs = [doc_id for doc_id, count in doc_id_counts.items() if count > 1]
    logger.info(f"Found {len(duplicate_docs)} document IDs with multiple entries")
    
    # Show sample of duplicated document IDs
    if duplicate_docs:
        sample_size = min(5, len(duplicate_docs))
        logger.info(f"Sample of {sample_size} document IDs with multiple entries:")
        
        for i, doc_id in enumerate(duplicate_docs[:sample_size]):
            entry_count = doc_id_counts[doc_id]
            logger.info(f"  Document ID {doc_id}: {entry_count} entries")
            
            # Show metadata differences for one sample
            if i == 0:
                entries = doc_id_to_entries[doc_id]
                logger.info(f"  Metadata differences for document ID {doc_id}:")
                
                # Get metadata fields from all entries
                all_fields = set()
                for entry_id in entries:
                    metadata = documents[entry_id].get('metadata', {})
                    all_fields.update(metadata.keys())
                
                # Show differences in key fields
                key_fields = ['chunk_id', 'chunk_index', 'page_number', 'file_path']
                key_fields = [f for f in key_fields if f in all_fields]
                
                # Show table header
                header = "  Entry ID"
                for field in key_fields:
                    header += f" | {field}"
                logger.info(header)
                
                # Show table rows
                for entry_id in entries[:10]:  # Show first 10 entries
                    metadata = documents[entry_id].get('metadata', {})
                    row = f"  {entry_id[:8]}..."
                    for field in key_fields:
                        value = metadata.get(field, 'N/A')
                        row += f" | {value}"
                    logger.info(row)

def analyze_chunk_ids(documents: Dict[str, Any]):
    """Analyze chunk IDs to understand how they relate to document IDs."""
    # Store document_id -> chunk_ids mappings
    doc_to_chunks = {}
    
    # Store chunk_id -> count mappings
    chunk_id_counts = Counter()
    
    for entry_id, doc in documents.items():
        metadata = doc.get('metadata', {})
        if 'document_id' in metadata and 'chunk_id' in metadata:
            doc_id = metadata['document_id']
            chunk_id = metadata['chunk_id']
            
            if doc_id not in doc_to_chunks:
                doc_to_chunks[doc_id] = set()
            doc_to_chunks[doc_id].add(chunk_id)
            
            chunk_id_counts[chunk_id] += 1
    
    # Count chunks per document
    chunks_per_doc = [(doc_id, len(chunks)) for doc_id, chunks in doc_to_chunks.items()]
    chunks_per_doc.sort(key=lambda x: x[1], reverse=True)
    
    logger.info(f"Top 10 documents by chunk count:")
    for doc_id, chunk_count in chunks_per_doc[:10]:
        logger.info(f"  Document ID {doc_id}: {chunk_count} chunks")
    
    # Find duplicate chunk IDs
    duplicate_chunks = [chunk_id for chunk_id, count in chunk_id_counts.items() if count > 1]
    logger.info(f"Found {len(duplicate_chunks)} duplicate chunk IDs")
    
    if duplicate_chunks:
        sample_size = min(5, len(duplicate_chunks))
        logger.info(f"Sample of {sample_size} duplicate chunk IDs:")
        for chunk_id in duplicate_chunks[:sample_size]:
            logger.info(f"  Chunk ID {chunk_id}: {chunk_id_counts[chunk_id]} occurrences")

if __name__ == "__main__":
    analyze_vector_store()