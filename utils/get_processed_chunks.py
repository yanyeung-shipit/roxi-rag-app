"""
Utility script to get processed chunk IDs from the vector store.
"""
import os
import sys
import logging
import json
from typing import Set

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent directory to path for imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# Import VectorStore class
from utils.vector_store import VectorStore

def get_processed_chunk_ids(force_refresh=False) -> Set[int]:
    """
    Get the set of chunk IDs that have been processed and added to the vector store.
    
    Args:
        force_refresh (bool): If True, force a refresh of the cache
    
    Returns:
        Set[int]: Set of processed chunk IDs
    """
    try:
        # Initialize VectorStore and use its get_processed_chunk_ids method with caching
        vector_store = VectorStore()
        processed_ids = vector_store.get_processed_chunk_ids(force_refresh=force_refresh)
        return processed_ids
    except Exception as e:
        logger.error(f"Error loading vector store data: {e}")
        return set()

def analyze_document_chunks():
    """Analyze the chunks in the vector store vs. database."""
    try:
        # Add the parent directory to the path so imports work correctly
        import os
        import sys
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # Now import should work
        from app import app, db
        from models import DocumentChunk
        
        # Get processed chunk IDs
        processed_ids = get_processed_chunk_ids()
        
        with app.app_context():
            # Get total chunks in database
            total_chunks = DocumentChunk.query.count()
            
            # Get chunk IDs from database
            db_chunk_ids = {chunk.id for chunk in DocumentChunk.query.all()}
            
            # Chunks in DB but not in vector store
            missing_in_vector = db_chunk_ids - processed_ids
            
            # Chunks in vector store but not in DB (shouldn't happen normally)
            missing_in_db = processed_ids - db_chunk_ids
            
            # Calculate processing rate
            if total_chunks > 0:
                processing_rate = len(processed_ids) / total_chunks * 100
            else:
                processing_rate = 0
            
            # Log results
            logger.info(f"Total chunks in database: {total_chunks}")
            logger.info(f"Processed chunks in vector store: {len(processed_ids)}")
            logger.info(f"Processing rate: {processing_rate:.2f}%")
            logger.info(f"Chunks missing from vector store: {len(missing_in_vector)}")
            logger.info(f"Chunks in vector store but not in DB: {len(missing_in_db)}")
            
            # Return results
            return {
                "total_chunks": total_chunks,
                "processed_chunks": len(processed_ids),
                "processing_rate": processing_rate,
                "missing_in_vector": len(missing_in_vector),
                "missing_in_db": len(missing_in_db)
            }
    except Exception as e:
        logger.error(f"Error analyzing document chunks: {e}")
        return {}

if __name__ == "__main__":
    # Get processed chunk IDs
    processed_ids = get_processed_chunk_ids()
    logger.info(f"Found {len(processed_ids)} processed chunk IDs")
    
    # Analyze document chunks
    analysis = analyze_document_chunks()
    
    # Print results as JSON
    print(json.dumps(analysis, indent=2))