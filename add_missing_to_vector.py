import os
import logging
import sys
import pickle
import psycopg2
import psycopg2.extras
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])

logger = logging.getLogger(__name__)

def add_missing_documents_to_vector():
    """
    This script adds missing database documents to the vector store by directly
    creating simple document entries for them.
    
    These entries won't have embeddings but will have citation information and metadata,
    serving as placeholders until they can be properly processed in the future.
    """
    try:
        DB_URL = os.environ.get("DATABASE_URL", "sqlite:///instance/app.db")
        
        # Load the vector store data
        logger.info("Loading vector store data from document_data.pkl")
        
        # Create a backup before making changes
        backup_name = f"document_data.pkl.bak.add_missing.{int(os.path.getmtime('document_data.pkl'))}"
        logger.info(f"Creating backup at {backup_name}")
        with open("document_data.pkl", "rb") as f_src:
            with open(backup_name, "wb") as f_dst:
                f_dst.write(f_src.read())
        
        with open("document_data.pkl", "rb") as f:
            vector_store_data = pickle.load(f)
        
        # Get documents from vector store
        documents = vector_store_data.get("documents", {})
        logger.info(f"Vector store has {len(documents)} total documents")
        
        # Get document counts from vector store
        document_counts = vector_store_data.get("document_counts", {})
        
        # Create a mapping of filenames and DOIs to vector store document IDs
        vs_filename_to_id = {}
        vs_doi_to_id = {}
        
        for doc_id, doc_data in documents.items():
            metadata = doc_data.get("metadata", {})
            if metadata.get("source_type") == "pdf":
                filename = metadata.get("filename")
                doi = metadata.get("doi")
                
                if filename:
                    vs_filename_to_id[filename] = doc_id
                if doi:
                    vs_doi_to_id[doi] = doc_id
        
        logger.info(f"Found {len(vs_filename_to_id)} unique filenames and {len(vs_doi_to_id)} unique DOIs in vector store")
        
        # Get metadata from database
        if DB_URL.startswith("postgresql://"):
            logger.info("Connecting to database to get PDF metadata")
            with psycopg2.connect(DB_URL) as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    # Get all PDF documents from the database
                    cursor.execute("""
                        SELECT d.id, d.file_path, d.filename, d.title, d.formatted_citation, 
                               d.doi, d.authors, d.journal, d.publication_year, d.volume, d.issue, d.pages
                        FROM documents d
                        WHERE d.file_type = 'pdf'
                    """)
                    
                    rows = cursor.fetchall()
                    logger.info(f"Found {len(rows)} PDF documents in database")
                    
                    added_count = 0
                    
                    # For each database document, check if it exists in vector store
                    for row in rows:
                        db_id = row["id"]
                        file_path = row["file_path"]
                        filename = row["filename"]
                        title = row["title"]
                        formatted_citation = row["formatted_citation"]
                        doi = row["doi"]
                        
                        # Skip if already in vector store
                        if filename in vs_filename_to_id or (doi and doi in vs_doi_to_id):
                            continue
                        
                        # This document needs to be added to vector store
                        logger.info(f"Adding missing document to vector store: {filename}")
                        
                        # Generate a new UUID for this document
                        new_id = str(uuid.uuid4())
                        
                        # Create a basic document entry
                        documents[new_id] = {
                            "id": new_id,
                            "text": f"Document placeholder for {filename}. This document has not been fully processed yet.",
                            "metadata": {
                                "source_type": "pdf",
                                "filename": filename,
                                "title": title or filename,
                                "db_id": db_id,
                                "file_path": file_path,
                                "doi": doi,
                                "citation": formatted_citation,
                                "formatted_citation": formatted_citation
                            }
                        }
                        
                        # Update document counts
                        if "pdf" in document_counts:
                            document_counts["pdf"] += 1
                        else:
                            document_counts["pdf"] = 1
                        
                        added_count += 1
                    
                    logger.info(f"Added {added_count} missing documents to vector store")
                    
                    # Save the updated vector store
                    logger.info("Saving updated vector store")
                    with open("document_data.pkl", "wb") as f:
                        pickle.dump(vector_store_data, f)
                    
                    logger.info("Vector store updated successfully!")
                    
                    return added_count
        else:
            logger.error("Only PostgreSQL database is supported")
            return 0
                
    except Exception as e:
        logger.error(f"Error adding missing documents to vector store: {e}")
        import traceback
        traceback.print_exc()
        return 0

if __name__ == "__main__":
    add_missing_documents_to_vector()