#!/usr/bin/env python3
"""
Simple script to check the current progress of vector store rebuilding.
This is meant to be a standalone tool that can be run at any time.
"""

import json
import os
import pickle
import sys
import argparse
from typing import Dict, Set, Any

# Configure logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Constants
DOCUMENT_DATA_FILE = "document_data.pkl"  # Vector store data file

def get_processed_chunk_ids() -> Set[int]:
    """Get IDs of chunks that have already been processed from the vector store."""
    try:
        # We need to extract chunk IDs from the document metadata in the vector store
        processed_ids = set()
        
        # Load document data from the pickle file
        if os.path.exists(DOCUMENT_DATA_FILE):
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
                            # Skip if chunk_id is not a valid integer
                            pass
            
            logger.info(f"Found {len(processed_ids)} processed chunk IDs in vector store")
        else:
            logger.warning(f"Vector store data file {DOCUMENT_DATA_FILE} not found")
        
        return processed_ids
    except Exception as e:
        logger.error(f"Error getting processed chunk IDs: {e}")
        return set()

def check_progress(json_output=False):
    """
    Check the progress of vector store rebuilding.
    
    Args:
        json_output (bool): If True, print output as JSON
        
    Returns:
        dict: Progress data
    """
    try:
        # Import these here to avoid errors when run from outside Flask app context
        from flask import Flask
        from app import app, db
        from models import Document, DocumentChunk
        from sqlalchemy import func
        
        # Get counts within Flask app context
        with app.app_context():
            # Get database stats
            session = db.session
            total_chunks = session.query(func.count(DocumentChunk.id)).scalar()
            total_docs = session.query(func.count(Document.id)).scalar()
            
            # Get vector store stats
            processed_ids = get_processed_chunk_ids()
            processed_chunks = len(processed_ids)
            
            # Calculate progress
            percentage = (processed_chunks / total_chunks * 100) if total_chunks > 0 else 0
            remaining_chunks = total_chunks - processed_chunks
            chunks_needed_for_75_percent = int(total_chunks * 0.75) - processed_chunks
            
            # Estimate time remaining (assuming 5 seconds per chunk as a rough estimate)
            est_seconds = remaining_chunks * 5
            est_minutes = est_seconds // 60
            est_hours = est_minutes // 60
            est_minutes %= 60
            
            # For 75% target
            est_seconds_75 = chunks_needed_for_75_percent * 5
            est_minutes_75 = est_seconds_75 // 60
            est_hours_75 = est_minutes_75 // 60
            est_minutes_75 %= 60
            
            # Prepare result
            result = {
                "vector_store_chunks": processed_chunks,
                "database_chunks": total_chunks,
                "total_documents": total_docs,
                "progress_percentage": percentage,
                "remaining_chunks": remaining_chunks,
                "estimated_hours": est_hours,
                "estimated_minutes": est_minutes,
                "for_75_percent": {
                    "chunks_needed": chunks_needed_for_75_percent,
                    "estimated_hours": est_hours_75,
                    "estimated_minutes": est_minutes_75,
                    "status": "Complete" if percentage >= 75.0 else "In progress"
                }
            }
            
            if json_output:
                print(json.dumps(result, indent=2))
            else:
                print("=" * 50)
                print("VECTOR STORE REBUILD PROGRESS")
                print("=" * 50)
                print(f"Vector store:      {processed_chunks}/{total_chunks} chunks")
                print(f"                   {percentage:.1f}% complete")
                print(f"Documents:         {total_docs} total in database")
                print(f"Remaining:         {remaining_chunks} chunks")
                print(f"Est. time (total): {est_hours}h {est_minutes}m")
                print("-" * 50)
                print("75% TARGET STATUS")
                if percentage >= 75.0:
                    print("Target achieved! Current: {:.1f}%".format(percentage))
                else:
                    print(f"Needed:           {chunks_needed_for_75_percent} more chunks to reach 75%")
                    print(f"Est. time (75%):  {est_hours_75}h {est_minutes_75}m")
                print("=" * 50)
                
            return result
    except ImportError:
        logger.error("Failed to import required modules. Make sure this script is run in the main directory.")
        if json_output:
            print(json.dumps({"error": "Import error - run script in main directory"}))
        else:
            print("ERROR: Run this script in the main directory with the Flask app.")
        return {"error": "import_error"}
    except Exception as e:
        logger.error(f"Error checking progress: {e}")
        if json_output:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"ERROR: {e}")
        return {"error": str(e)}

def main():
    """Main function to run the script."""
    parser = argparse.ArgumentParser(description="Check the progress of vector store rebuilding")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    check_progress(json_output=args.json)

if __name__ == "__main__":
    main()