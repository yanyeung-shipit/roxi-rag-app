"""
Script to check our progress in rebuilding the vector store.
This script logs progress information and returns structured data
that can be used by other scripts.
"""
import sys
import json
import logging
from datetime import datetime
from app import app, Document, DocumentChunk
from utils.vector_store import VectorStore

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def check_progress(json_output=False):
    """
    Check the progress of rebuilding the vector store.
    
    Args:
        json_output (bool): If True, print JSON output to stdout instead of human-readable.
        
    Returns:
        dict: Progress information as a dictionary
    """
    try:
        # Get vector store stats
        vector_store = VectorStore()
        vector_stats = vector_store.get_stats()
        
        # Get database stats
        with app.app_context():
            # Get document counts
            db_doc_count = Document.query.count()
            db_chunk_count = DocumentChunk.query.count()
            
            # Get counts of chunks per document
            doc_with_chunks = Document.query.filter(Document.chunks.any()).all()
            doc_with_chunks_count = len(doc_with_chunks)
            
            # Get unprocessed documents (have chunks but no vector embeddings yet)
            # This is an approximation since we don't track which document each vector belongs to
            docs_unprocessed = db_doc_count - (vector_stats.get('pdfs', 0) + vector_stats.get('websites', 0))
            if docs_unprocessed < 0:
                docs_unprocessed = 0
                
            # Calculate progress percentages
            chunk_progress = vector_stats['total_documents'] / db_chunk_count * 100 if db_chunk_count > 0 else 0
            doc_progress = (vector_stats.get('pdfs', 0) + vector_stats.get('websites', 0)) / db_doc_count * 100 if db_doc_count > 0 else 0
            
            # Time estimate (very rough)
            chunks_remaining = db_chunk_count - vector_stats['total_documents']
            seconds_per_chunk = 3  # Assuming 3 seconds per chunk for embedding
            estimated_seconds_remaining = chunks_remaining * seconds_per_chunk
            estimated_hours = estimated_seconds_remaining // 3600
            estimated_minutes = (estimated_seconds_remaining % 3600) // 60
            
            # Prepare structured data
            result = {
                "timestamp": datetime.now().isoformat(),
                "vector_chunks": vector_stats['total_documents'],
                "db_chunks": db_chunk_count,
                "db_docs": db_doc_count,
                "progress_percent": chunk_progress,
                "chunks_remaining": chunks_remaining,
                "docs_with_chunks": doc_with_chunks_count,
                "docs_unprocessed": docs_unprocessed,
                "vector_stats": vector_stats,
                "estimate": {
                    "seconds_remaining": estimated_seconds_remaining,
                    "hours": int(estimated_hours),
                    "minutes": int(estimated_minutes)
                }
            }
            
            # If JSON output is requested, print as JSON and return
            if json_output:
                print(json.dumps(result, indent=2))
                return result
            
            # Print human-readable report
            logger.info("=" * 40)
            logger.info("VECTOR STORE REBUILD PROGRESS")
            logger.info("=" * 40)
            logger.info(f"Vector store:   {vector_stats['total_documents']} chunks")
            logger.info(f"Database:       {db_chunk_count} chunks in {db_doc_count} documents")
            logger.info("-" * 40)
            logger.info(f"Progress:       {vector_stats['total_documents']}/{db_chunk_count} chunks")
            logger.info(f"                {chunk_progress:.1f}% complete")
            
            # Add time estimate if chunks are remaining
            if chunks_remaining > 0:
                logger.info(f"Remaining:      {chunks_remaining} chunks")
                logger.info(f"Est. time:      {estimated_hours}h {estimated_minutes}m remaining")
            
            logger.info("=" * 40)
            
            return result
    
    except Exception as e:
        logger.error(f"Error checking progress: {e}")
        if json_output:
            print(json.dumps({"error": str(e)}))
        return {"error": str(e)}

if __name__ == "__main__":
    # Check if JSON output is requested
    json_output = "--json" in sys.argv
    # Run the progress check
    check_progress(json_output=json_output)