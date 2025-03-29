import os
import logging
import sys
import pickle
import psycopg2
import psycopg2.extras
import faiss

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])

logger = logging.getLogger(__name__)

# Get DATABASE_URL from environment
DB_URL = os.environ.get("DATABASE_URL", "sqlite:///instance/app.db")

def sync_citations_from_db_to_vector_store():
    """
    This script directly syncs citations from the database to the vector store.
    It's a simpler approach than trying to extract citations from PDFs again.
    """
    try:
        # Load the vector store data
        logger.info("Loading vector store data from document_data.pkl")
        with open("document_data.pkl", "rb") as f:
            vector_store_data = pickle.load(f)
        
        # Make a backup
        backup_path = f"document_data.pkl.bak.sync"
        logger.info(f"Creating backup at {backup_path}")
        with open(backup_path, "wb") as f:
            pickle.dump(vector_store_data, f)
        
        # Get citations from database
        logger.info("Connecting to database to get citations")
        if DB_URL.startswith("postgresql://"):
            # Connect to PostgreSQL
            with psycopg2.connect(DB_URL) as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("""
                        SELECT id, file_path, filename, title, formatted_citation, doi
                        FROM documents
                        WHERE file_type = 'pdf' AND formatted_citation IS NOT NULL
                    """)
                    
                    rows = cursor.fetchall()
                    logger.info(f"Found {len(rows)} documents with citations in database")
                    
                    # Get documents from vector store
                    documents = vector_store_data.get("documents", {})
                    logger.info(f"Vector store has {len(documents)} total documents")
                    
                    updated_count = 0
                    pdf_docs_count = 0
                    
                    # Count PDF documents in vector store
                    for doc_id, doc_data in documents.items():
                        metadata = doc_data.get("metadata", {})
                        if metadata.get("source_type") == "pdf":
                            pdf_docs_count += 1
                    
                    logger.info(f"Vector store has {pdf_docs_count} PDF documents")
                    
                    # Create lookup by file_path
                    for row in rows:
                        file_path = row["file_path"]
                        citation = row["formatted_citation"]
                        doi = row["doi"]
                        
                        if not file_path or not citation:
                            continue
                        
                        filename = row["filename"]
                        
                        # Look for documents with this file_path or matching filename
                        for doc_id, doc_data in documents.items():
                            metadata = doc_data.get("metadata", {})
                            
                            # Try different ways to match the document
                            matched = False
                            
                            # Match by file_path if present
                            if metadata.get("source_type") == "pdf" and metadata.get("file_path") == file_path:
                                matched = True
                            
                            # Match by filename if present
                            elif metadata.get("source_type") == "pdf" and metadata.get("filename") == filename:
                                matched = True
                            
                            # Match by title if present (assuming filename can be part of the title)
                            elif metadata.get("source_type") == "pdf" and filename and metadata.get("title") and filename in metadata.get("title"):
                                matched = True
                                
                            if matched:
                                # Update citation
                                metadata["formatted_citation"] = citation
                                metadata["citation"] = citation
                                if doi:
                                    metadata["doi"] = doi
                                updated_count += 1
                                logger.info(f"Updated citation for document: {filename}")
        
        logger.info(f"Updated {updated_count} documents in vector store")
        
        # Save the updated vector store
        logger.info("Saving updated vector store")
        with open("document_data.pkl", "wb") as f:
            pickle.dump(vector_store_data, f)
            
        logger.info("Vector store updated successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Error updating vector store: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    sync_citations_from_db_to_vector_store()