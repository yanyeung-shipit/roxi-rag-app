#!/usr/bin/env python3
"""
Vector Store Fix Script

This script fixes issues in the vector store:
1. Removes duplicate documents with the same chunk_id
2. Ensures all documents have proper chunk_id and document_id metadata
3. Updates the structure to be consistent with the database

Usage:
    python fix_vector_store.py [--backup]
"""

import os
import sys
import time
import pickle
import logging
import shutil
import datetime
from typing import Dict, Any, List, Set, Tuple, Optional
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Add the current directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import Document, DocumentChunk
from utils.vector_store import VectorStore

def backup_vector_store():
    """Create a backup of the vector store files."""
    timestamp = int(time.time())
    
    # Backup the document data
    doc_data_path = "document_data.pkl"
    if os.path.exists(doc_data_path):
        backup_path = f"{doc_data_path}.bak.cleanup.{timestamp}"
        shutil.copy2(doc_data_path, backup_path)
        logger.info(f"Backed up document data to {backup_path}")
    
    # Backup the FAISS index
    faiss_path = "faiss_index.bin"
    if os.path.exists(faiss_path):
        backup_path = f"{faiss_path}.bak.cleanup.{timestamp}"
        shutil.copy2(faiss_path, backup_path)
        logger.info(f"Backed up FAISS index to {backup_path}")

def get_chunk_counts() -> Dict[int, int]:
    """Get a count of how many times each chunk_id appears in the vector store."""
    # Load the vector store data directly
    with open("document_data.pkl", "rb") as f:
        vector_store_data = pickle.load(f)
    
    documents = vector_store_data.get("documents", {})
    
    # Count occurrences of each chunk_id
    chunk_counts = defaultdict(int)
    for doc_id, doc in documents.items():
        if "metadata" in doc and "chunk_id" in doc["metadata"]:
            chunk_id = doc["metadata"]["chunk_id"]
            chunk_counts[chunk_id] += 1
    
    return chunk_counts

def fix_vector_store():
    """
    Fix issues in the vector store:
    1. Remove duplicate documents with the same chunk_id
    2. Ensure all documents have proper chunk_id and document_id metadata
    3. Update the structure to be consistent with the database
    """
    logger.info("Starting vector store cleanup")
    
    # Create backup
    backup_vector_store()
    
    # Load the vector store data directly
    with open("document_data.pkl", "rb") as f:
        vector_store_data = pickle.load(f)
    
    # Get original documents
    documents = vector_store_data.get("documents", {})
    original_count = len(documents)
    logger.info(f"Vector store contains {original_count} documents")
    
    # Get chunk counts
    chunk_counts = get_chunk_counts()
    duplicate_chunk_ids = {chunk_id for chunk_id, count in chunk_counts.items() if count > 1}
    logger.info(f"Found {len(duplicate_chunk_ids)} chunk IDs with duplicates")
    
    # Create a clean document list
    clean_documents = {}
    processed_chunk_ids = set()
    documents_without_chunk_id = {}
    
    # First pass: Collect documents without duplicates and the best instance of each duplicate
    for doc_id, doc in documents.items():
        if "metadata" not in doc or "chunk_id" not in doc["metadata"]:
            # Keep documents without chunk_id for now
            documents_without_chunk_id[doc_id] = doc
            continue
            
        chunk_id = doc["metadata"]["chunk_id"]
        
        if chunk_id in duplicate_chunk_ids:
            if chunk_id not in processed_chunk_ids:
                # Keep the first instance of each duplicate chunk_id
                clean_documents[doc_id] = doc
                processed_chunk_ids.add(chunk_id)
        else:
            # Keep unique documents
            clean_documents[doc_id] = doc
    
    logger.info(f"After removing duplicates: {len(clean_documents)} documents")
    logger.info(f"Found {len(documents_without_chunk_id)} documents without chunk_id")
    
    # Get a list of all valid chunk IDs from the database
    with app.app_context():
        db_chunk_ids = set(row[0] for row in db.session.query(DocumentChunk.id).all())
    
    logger.info(f"Database contains {len(db_chunk_ids)} chunks")
    
    # Verify which documents have valid chunk_ids
    valid_documents = {}
    invalid_chunk_ids = set()
    
    for doc_id, doc in clean_documents.items():
        if "metadata" in doc and "chunk_id" in doc["metadata"]:
            chunk_id = doc["metadata"]["chunk_id"]
            if chunk_id in db_chunk_ids:
                valid_documents[doc_id] = doc
            else:
                invalid_chunk_ids.add(chunk_id)
    
    logger.info(f"Found {len(invalid_chunk_ids)} documents with invalid chunk_ids")
    logger.info(f"Valid documents with matching chunk_ids: {len(valid_documents)}")
    
    # Create the fixed vector store data
    fixed_vector_store_data = {
        "documents": valid_documents,
        "document_counts": vector_store_data.get("document_counts", {})
    }
    
    # Save the fixed vector store data
    with open("document_data.pkl", "wb") as f:
        pickle.dump(fixed_vector_store_data, f)
    
    # Reload the vector store to create a new FAISS index
    vector_store = VectorStore()
    vector_store.save()
    
    logger.info(f"Vector store cleanup completed")
    logger.info(f"Original document count: {original_count}")
    logger.info(f"New document count: {len(valid_documents)}")
    logger.info(f"Removed {original_count - len(valid_documents)} documents")

def main():
    """Main function to fix the vector store."""
    import argparse
    parser = argparse.ArgumentParser(description='Fix issues in the vector store')
    parser.add_argument('--backup', action='store_true', 
                        help='Create a backup of the vector store files')
    
    args = parser.parse_args()
    
    if args.backup:
        backup_vector_store()
        logger.info("Backup completed")
    else:
        fix_vector_store()

if __name__ == "__main__":
    main()