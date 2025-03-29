import os
import logging
import sys
import pickle
import psycopg2
import psycopg2.extras

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])

logger = logging.getLogger(__name__)

# Get DATABASE_URL from environment
DB_URL = os.environ.get("DATABASE_URL", "sqlite:///instance/app.db")

def inspect_documents():
    """
    Inspect documents in both the database and vector store to understand why
    we can't match them correctly.
    """
    try:
        # Load the vector store data
        logger.info("Loading vector store data from document_data.pkl")
        with open("document_data.pkl", "rb") as f:
            vector_store_data = pickle.load(f)
        
        # Get documents from vector store
        documents = vector_store_data.get("documents", {})
        logger.info(f"Vector store has {len(documents)} total documents")
        
        # Count and analyze PDF documents in vector store
        pdf_docs = []
        
        for doc_id, doc_data in documents.items():
            metadata = doc_data.get("metadata", {})
            if metadata.get("source_type") == "pdf":
                pdf_docs.append((doc_id, metadata))
        
        logger.info(f"Vector store has {len(pdf_docs)} PDF documents")
        
        # Show example PDF metadata
        if pdf_docs:
            logger.info("Example PDF document metadata from vector store:")
            for i, (doc_id, metadata) in enumerate(pdf_docs[:3]):
                logger.info(f"Document {i+1} ID: {doc_id}")
                for key, value in metadata.items():
                    logger.info(f"  {key}: {value}")
        
        # Get documents from database
        if DB_URL.startswith("postgresql://"):
            # Connect to PostgreSQL
            with psycopg2.connect(DB_URL) as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("""
                        SELECT id, file_path, filename, title, formatted_citation, doi
                        FROM documents
                        WHERE file_type = 'pdf'
                        LIMIT 3
                    """)
                    
                    rows = cursor.fetchall()
                    
                    logger.info("Example PDF documents from database:")
                    for i, row in enumerate(rows):
                        logger.info(f"Document {i+1} ID: {row['id']}")
                        logger.info(f"  filename: {row['filename']}")
                        logger.info(f"  file_path: {row['file_path']}")
                        logger.info(f"  title: {row['title']}")
                        logger.info(f"  citation: {row['formatted_citation']}")
        
        # Now examine the first vector store entries to see if there's another identifier
        logger.info("Full document info for first PDF document:")
        if pdf_docs:
            doc_id, _ = pdf_docs[0]
            doc_data = documents[doc_id]
            logger.info(f"Document ID: {doc_id}")
            for key, value in doc_data.items():
                if key != "metadata":
                    logger.info(f"  {key}: {value}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error inspecting documents: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    inspect_documents()