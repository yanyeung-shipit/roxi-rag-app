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

def diagnose_citations():
    """
    Print diagnostic information about citations in the vector store.
    """
    try:
        # Load the vector store data
        logger.info("Loading vector store data from document_data.pkl")
        with open("document_data.pkl", "rb") as f:
            vector_store_data = pickle.load(f)
        
        # Get documents from vector store
        documents = vector_store_data.get("documents", {})
        logger.info(f"Vector store has {len(documents)} total documents")
        
        # Count documents with citation data
        pdf_docs_with_citation = 0
        pdf_docs_with_formatted_citation = 0
        pdf_docs_with_unnamed = 0
        pdf_docs_total = 0
        
        for doc_id, doc_data in documents.items():
            metadata = doc_data.get("metadata", {})
            if metadata.get("source_type") == "pdf":
                pdf_docs_total += 1
                
                if metadata.get("citation"):
                    pdf_docs_with_citation += 1
                    
                if metadata.get("formatted_citation"):
                    pdf_docs_with_formatted_citation += 1
                    
                # Check for unnamed citations
                citation = metadata.get("citation", "")
                formatted_citation = metadata.get("formatted_citation", "")
                if "Unnamed PDF" in citation or "Unnamed PDF" in formatted_citation:
                    pdf_docs_with_unnamed += 1
        
        logger.info(f"Found {pdf_docs_total} PDF documents in vector store")
        logger.info(f"  {pdf_docs_with_citation} have 'citation' field")
        logger.info(f"  {pdf_docs_with_formatted_citation} have 'formatted_citation' field")
        logger.info(f"  {pdf_docs_with_unnamed} have 'Unnamed PDF' in their citation")
        
        # Show examples of problematic PDF documents
        logger.info("\nExample PDF documents with 'Unnamed PDF' in their citation:")
        count = 0
        for doc_id, doc_data in documents.items():
            metadata = doc_data.get("metadata", {})
            if metadata.get("source_type") == "pdf":
                citation = metadata.get("citation", "")
                formatted_citation = metadata.get("formatted_citation", "")
                
                if "Unnamed PDF" in citation or "Unnamed PDF" in formatted_citation:
                    if count < 5:  # Show examples for first 5
                        logger.info(f"\nPDF document #{count+1} with ID {doc_id}:")
                        logger.info(f"  Title: {metadata.get('title', 'No title')}")
                        logger.info(f"  Filename: {metadata.get('filename', 'No filename')}")
                        logger.info(f"  File path: {metadata.get('file_path', 'No file path')}")
                        logger.info(f"  DOI: {metadata.get('doi', 'No DOI')}")
                        logger.info(f"  Citation: {citation}")
                        logger.info(f"  Formatted citation: {formatted_citation}")
                        count += 1
        
        # Check database entries
        DB_URL = os.environ.get("DATABASE_URL", "sqlite:///instance/app.db")
        if DB_URL.startswith("postgresql://"):
            logger.info("\nChecking database for PDF documents:")
            
            try:
                with psycopg2.connect(DB_URL) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                        cursor.execute("SELECT COUNT(*) FROM documents WHERE file_type = 'pdf'")
                        result = cursor.fetchone()
                        db_pdf_count = result[0] if result else 0
                        logger.info(f"Database has {db_pdf_count} PDF documents")
                        
                        # Count documents with untitled
                        cursor.execute("""
                            SELECT COUNT(*) 
                            FROM documents
                            WHERE file_type = 'pdf' AND (title IS NULL OR title = '' OR title = 'untitled' OR title = 'Unnamed PDF')
                        """)
                        
                        result = cursor.fetchone()
                        db_untitled_count = result[0] if result else 0
                        logger.info(f"Database has {db_untitled_count} PDF documents with empty/untitled title")
                        
                        # Get examples of problematic database entries
                        cursor.execute("""
                            SELECT id, file_path, filename, title, formatted_citation, doi
                            FROM documents
                            WHERE file_type = 'pdf' AND (title IS NULL OR title = '' OR title = 'untitled' OR title = 'Unnamed PDF')
                            LIMIT 5
                        """)
                        
                        # Show examples of problematic database entries
                        rows = cursor.fetchall()
                        if rows:
                            logger.info("\nExample problematic PDF documents in database:")
                            for row in rows:
                                logger.info(f"\nDatabase document with ID {row['id']}:")
                                logger.info(f"  Title: {row['title'] or 'No title'}")
                                logger.info(f"  Filename: {row['filename'] or 'No filename'}")
                                logger.info(f"  File path: {row['file_path'] or 'No file path'}")
                                logger.info(f"  DOI: {row['doi'] or 'No DOI'}")
                                logger.info(f"  Formatted citation: {row['formatted_citation'] or 'No formatted citation'}")
                                
                                # Try to find this document in the vector store
                                found = False
                                for doc_id, doc_data in documents.items():
                                    metadata = doc_data.get("metadata", {})
                                    
                                    if ((metadata.get("file_path") and row["file_path"] and 
                                         metadata.get("file_path") == row["file_path"]) or
                                        (metadata.get("filename") and row["filename"] and 
                                         metadata.get("filename") == row["filename"]) or
                                        (metadata.get("doi") and row["doi"] and 
                                         metadata.get("doi") == row["doi"])):
                                        
                                        found = True
                                        logger.info(f"  MATCHED with vector store document ID: {doc_id}")
                                        break
                                
                                if not found:
                                    logger.info(f"  NOT FOUND in vector store!")
                        
                        # Find documents in DB with proper citations that are not in vector store
                        cursor.execute("""
                            SELECT id, file_path, filename, title, formatted_citation, doi
                            FROM documents
                            WHERE file_type = 'pdf' AND formatted_citation IS NOT NULL AND formatted_citation != ''
                            LIMIT 10
                        """)
                        
                        rows = cursor.fetchall()
                        logger.info("\nChecking if DB documents with good citations are found in vector store:")
                        for row in rows:
                            # Try to find this document in the vector store
                            found = False
                            for doc_id, doc_data in documents.items():
                                metadata = doc_data.get("metadata", {})
                                
                                if ((metadata.get("file_path") and row["file_path"] and 
                                     metadata.get("file_path") == row["file_path"]) or
                                    (metadata.get("filename") and row["filename"] and 
                                     metadata.get("filename") == row["filename"]) or
                                    (metadata.get("doi") and row["doi"] and 
                                     metadata.get("doi") == row["doi"])):
                                    
                                    found = True
                                    break
                            
                            if not found:
                                logger.info(f"DB document ID {row['id']} ({row['filename']}) has good citation but NOT FOUND in vector store!")
                        
            except Exception as e:
                logger.error(f"Error connecting to database: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error diagnosing citations: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    diagnose_citations()