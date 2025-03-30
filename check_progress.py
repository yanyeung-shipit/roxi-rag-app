#!/usr/bin/env python3
"""
Script to check our progress in rebuilding the vector store.
This script logs progress information and returns structured data
that can be used by other scripts.
"""

import os
import sys
import pickle
import json
import logging
from typing import Set, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger()

DOCUMENT_DATA_FILE = "document_data.pkl"

def check_progress(json_output=False):
    """
    Check the progress of rebuilding the vector store.
    
    Args:
        json_output (bool): If True, print JSON output to stdout instead of human-readable.
        
    Returns:
        dict: Progress information as a dictionary
    """
    try:
        # Get processed chunks from vector store
        processed_ids = set()
        if os.path.exists(DOCUMENT_DATA_FILE):
            try:
                with open(DOCUMENT_DATA_FILE, 'rb') as f:
                    loaded_data = pickle.load(f)
                    documents = loaded_data.get('documents', {})
                    
                    # Extract chunk_id from metadata if it exists
                    for doc_id, doc_data in documents.items():
                        metadata = doc_data.get('metadata', {})
                        if 'chunk_id' in metadata and metadata['chunk_id'] is not None:
                            try:
                                chunk_id = int(metadata['chunk_id'])
                                processed_ids.add(chunk_id)
                            except (ValueError, TypeError):
                                pass
                
                logger.info(f"Found {len(processed_ids)} processed chunk IDs in vector store")
            except Exception as e:
                logger.error(f"Error loading vector store data: {e}")
        else:
            logger.warning(f"Vector store data file {DOCUMENT_DATA_FILE} not found")
        
        # Get database info within Flask app context
        from app import app, db
        from models import DocumentChunk
        from sqlalchemy import func
        
        with app.app_context():
            # Count total chunks
            total_chunks = db.session.query(func.count(DocumentChunk.id)).scalar()
            
            # Calculate progress
            processed_count = len(processed_ids)
            if total_chunks > 0:
                percentage = (processed_count / total_chunks) * 100
            else:
                percentage = 0
                
            # Prepare result data
            result = {
                "total_chunks": total_chunks,
                "processed_chunks": processed_count,
                "percentage_complete": round(percentage, 2),
                "remaining_chunks": total_chunks - processed_count,
                "timestamp": None  # Will be filled in when converted to JSON
            }
            
            # Output
            if json_output:
                import datetime
                result["timestamp"] = datetime.datetime.now().isoformat()
                print(json.dumps(result, indent=2))
            else:
                logger.info(f"Progress: {processed_count}/{total_chunks} chunks ({percentage:.2f}%)")
                logger.info(f"Remaining: {total_chunks - processed_count} chunks")
            
            return result
    
    except Exception as e:
        error_msg = f"Error checking progress: {e}"
        logger.error(error_msg)
        
        if json_output:
            print(json.dumps({"error": error_msg}))
        
        return {"error": error_msg}

if __name__ == "__main__":
    # Check if JSON output is requested
    json_flag = "--json" in sys.argv
    check_progress(json_output=json_flag)