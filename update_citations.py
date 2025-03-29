import sys
import os
import logging
import json
import pickle
import numpy as np
import time
import sqlite3
from contextlib import closing

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])

logger = logging.getLogger(__name__)

# Import our citation handling functions
from utils.citation_manager import extract_citation_info, extract_doi_from_pdf

# Get DATABASE_URL from environment
import os
DB_URL = os.environ.get("DATABASE_URL", "sqlite:///instance/app.db")

def get_pdf_files_from_db():
    """Get all PDF files from the database with their file paths"""
    pdf_files = {}
    
    try:
        if DB_URL.startswith("sqlite:///"):
            # SQLite connection
            db_path = DB_URL.replace("sqlite:///", "")
            with closing(sqlite3.connect(db_path)) as conn:
                conn.row_factory = sqlite3.Row
                with closing(conn.cursor()) as cursor:
                    # Query all PDF documents with their paths
                    cursor.execute("""
                        SELECT id, filename, file_path, formatted_citation, doi
                        FROM documents
                        WHERE file_type = 'pdf' AND file_path IS NOT NULL
                        ORDER BY id DESC
                    """)
                    
                    rows = cursor.fetchall()
                    
                    for row in rows:
                        file_path = row['file_path']
                        if file_path and os.path.exists(file_path):
                            pdf_files[file_path] = {
                                "id": row['id'],
                                "filename": row['filename'],
                                "formatted_citation": row['formatted_citation'],
                                "doi": row['doi']
                            }
        elif DB_URL.startswith("postgresql://"):
            # PostgreSQL connection
            import psycopg2
            import psycopg2.extras
            
            logger.info("Connecting to PostgreSQL database")
            with psycopg2.connect(DB_URL) as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    # Query all PDF documents with their paths
                    cursor.execute("""
                        SELECT id, filename, file_path, formatted_citation, doi
                        FROM documents
                        WHERE file_type = 'pdf' AND file_path IS NOT NULL
                        ORDER BY id DESC
                    """)
                    
                    rows = cursor.fetchall()
                    
                    for row in rows:
                        file_path = row['file_path']
                        if file_path and os.path.exists(file_path):
                            pdf_files[file_path] = {
                                "id": row['id'],
                                "filename": row['filename'],
                                "formatted_citation": row['formatted_citation'],
                                "doi": row['doi']
                            }
        else:
            logger.error(f"Unknown database type: {DB_URL}")
            return {}
                        
        logger.info(f"Found {len(pdf_files)} PDF files in database")
        return pdf_files
    except Exception as e:
        logger.error(f"Error querying database: {e}")
        import traceback
        traceback.print_exc()
        return {}

def update_vector_store_citations():
    """
    This script updates the citation information for PDF documents in the vector store
    without having to reprocess the entire document.
    """
    # Path to the vector store data
    vector_store_path = "faiss_index.bin"
    
    # Load the vector store data
    try:
        logger.info(f"Loading vector store from {vector_store_path}")
        # Use faiss to read the index, just like in vector_store.py
        import faiss
        index = faiss.read_index(vector_store_path)
        
        # Now load document data from the pickle file
        data_path = "document_data.pkl"
        logger.info(f"Loading document data from {data_path}")
        with open(data_path, "rb") as f:
            loaded_data = pickle.load(f)
            
        # Make a backup of the original data
        backup_path = f"document_data.pkl.bak.{int(time.time())}"
        logger.info(f"Creating backup of document data at {backup_path}")
        with open(backup_path, "wb") as f:
            pickle.dump(loaded_data, f)
            
        # Extract the documents from the document data
        documents = loaded_data.get("documents", {})
        # Convert documents from a dictionary to a list of items with keys and values
        documents_list = []
        for doc_id, doc_data in documents.items():
            doc_data['id'] = doc_id  # Store the ID within the document data
            documents_list.append(doc_data)
            
        logger.info(f"First document structure: {documents_list[0] if documents_list else 'No documents'}")
        logger.info(f"Loaded {len(documents)} documents from vector store")
        
        # Get PDF files from database to ensure we have all file paths
        db_pdf_files = get_pdf_files_from_db()
        
        # Track statistics
        total_pdfs = 0
        updated_pdfs = 0
        
        # Collect PDF documents by file path
        pdf_files = {}
        for i, doc in enumerate(documents_list):
            metadata = doc.get("metadata", {})
            source_type = metadata.get("source_type")
            
            if source_type == "pdf":
                file_path = metadata.get("file_path")
                
                # Check if we have this file path in our database records
                if not file_path and "title" in metadata:
                    # Try to find the file path from the database by title
                    title = metadata.get("title")
                    for db_path, db_info in db_pdf_files.items():
                        if os.path.basename(db_path).startswith(title):
                            file_path = db_path
                            break
                
                if file_path and os.path.exists(file_path) and file_path.endswith(".pdf"):
                    total_pdfs += 1
                    
                    # Add to the collection of PDFs to process
                    if file_path not in pdf_files:
                        filename = os.path.basename(file_path)
                        pdf_files[file_path] = {
                            "filename": filename,
                            "indices": [i]
                        }
                    else:
                        pdf_files[file_path]["indices"].append(i)
        
        logger.info(f"Found {total_pdfs} PDF documents in vector store")
        logger.info(f"Found {len(pdf_files)} unique PDF files that need citation updating")
        
        # Process each PDF file
        for file_path, info in pdf_files.items():
            filename = info["filename"]
            indices = info["indices"]
            
            logger.info(f"Processing {filename} with {len(indices)} chunks")
            
            # Check if we already have this citation in the database
            db_citation = None
            doi = None
            
            # First check if this file is in our database records with a citation
            if file_path in db_pdf_files:
                db_info = db_pdf_files[file_path]
                if db_info["formatted_citation"]:
                    db_citation = db_info["formatted_citation"]
                    doi = db_info["doi"]
                    logger.info(f"Using existing citation from database: {db_citation}")
            
            if not db_citation:
                try:
                    # Extract citation information
                    citation, metadata = extract_citation_info(filename, file_path)
                    
                    if citation:
                        # Make sure metadata is not None
                        if metadata is None:
                            metadata = {}
                        formatted_citation = metadata.get("formatted_citation", citation)
                        doi = metadata.get("doi")
                        
                        logger.info(f"Extracted citation: {formatted_citation}")
                    else:
                        logger.warning(f"Could not extract citation for {filename}")
                        continue
                except Exception as e:
                    logger.error(f"Error processing {filename}: {e}")
                    continue
            else:
                # Use the citation from the database
                formatted_citation = db_citation
            
            # Update all chunks for this PDF in the vector store
            for idx in indices:
                document_id = documents_list[idx]["id"]
                if document_id in documents:
                    if "metadata" not in documents[document_id]:
                        documents[document_id]["metadata"] = {}
                    documents[document_id]["metadata"]["formatted_citation"] = formatted_citation
                    documents[document_id]["metadata"]["citation"] = formatted_citation
                    
                    if doi:
                        documents[document_id]["metadata"]["doi"] = doi
            
            # Also update the database if the citation was newly extracted
            if not db_citation and file_path in db_pdf_files:
                try:
                    db_id = db_pdf_files[file_path]["id"]
                    
                    if DB_URL.startswith("sqlite:///"):
                        # SQLite connection
                        db_path = DB_URL.replace("sqlite:///", "")
                        with closing(sqlite3.connect(db_path)) as conn:
                            with closing(conn.cursor()) as cursor:
                                cursor.execute("""
                                    UPDATE documents
                                    SET formatted_citation = ?, doi = ?
                                    WHERE id = ?
                                """, (formatted_citation, doi, db_id))
                                conn.commit()
                                logger.info(f"Updated database record for {filename}")
                    elif DB_URL.startswith("postgresql://"):
                        # PostgreSQL connection
                        import psycopg2
                        
                        with psycopg2.connect(DB_URL) as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("""
                                    UPDATE documents
                                    SET formatted_citation = %s, doi = %s
                                    WHERE id = %s
                                """, (formatted_citation, doi, db_id))
                                conn.commit()
                                logger.info(f"Updated PostgreSQL database record for {filename}")
                    else:
                        logger.error(f"Unknown database type: {DB_URL}")
                except Exception as e:
                    logger.error(f"Error updating database for {filename}: {e}")
                    import traceback
                    traceback.print_exc()
                    
            updated_pdfs += 1
                
        # Save the updated document data
        logger.info(f"Updated citations for {updated_pdfs} PDF files")
        logger.info(f"Saving updated document data to {data_path}")
        with open(data_path, "wb") as f:
            pickle.dump(loaded_data, f)
            
        logger.info("Vector store updated successfully!")
        
        # Now verify that any file in the database without a citation gets updated
        try:
            # Requery the database to find PDFs without citations
            if DB_URL.startswith("sqlite:///"):
                # SQLite connection
                db_path = DB_URL.replace("sqlite:///", "")
                with closing(sqlite3.connect(db_path)) as conn:
                    conn.row_factory = sqlite3.Row
                    with closing(conn.cursor()) as cursor:
                        cursor.execute("""
                            SELECT id, filename, file_path, formatted_citation
                            FROM documents
                            WHERE file_type = 'pdf' AND file_path IS NOT NULL 
                              AND (formatted_citation IS NULL OR formatted_citation = '')
                        """)
                        
                        rows = cursor.fetchall()
                        
                        if rows:
                            logger.info(f"Found {len(rows)} SQLite documents without citations")
                            
                            for row in rows:
                                file_path = row['file_path']
                                filename = row['filename']
                                
                                if os.path.exists(file_path):
                                    try:
                                        # Extract citation information
                                        citation, metadata = extract_citation_info(filename, file_path)
                                        
                                        if citation:
                                            # Make sure metadata is not None
                                            if metadata is None:
                                                metadata = {}
                                            formatted_citation = metadata.get("formatted_citation", citation)
                                            doi = metadata.get("doi")
                                            
                                            # Update the database
                                            cursor.execute("""
                                                UPDATE documents
                                                SET formatted_citation = ?, doi = ?
                                                WHERE id = ?
                                            """, (formatted_citation, doi, row['id']))
                                            conn.commit()
                                            
                                            logger.info(f"Updated database citation for {filename}: {formatted_citation}")
                                        else:
                                            logger.warning(f"Could not extract citation for {filename}")
                                    except Exception as e:
                                        logger.error(f"Error processing {filename}: {e}")
                        else:
                            logger.info("All SQLite documents have citations")
            
            elif DB_URL.startswith("postgresql://"):
                # PostgreSQL connection
                import psycopg2
                import psycopg2.extras
                
                with psycopg2.connect(DB_URL) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                        cursor.execute("""
                            SELECT id, filename, file_path, formatted_citation
                            FROM documents
                            WHERE file_type = 'pdf' AND file_path IS NOT NULL 
                              AND (formatted_citation IS NULL OR formatted_citation = '')
                        """)
                        
                        rows = cursor.fetchall()
                        
                        if rows:
                            logger.info(f"Found {len(rows)} PostgreSQL documents without citations")
                            
                            for row in rows:
                                file_path = row['file_path']
                                filename = row['filename']
                                
                                if os.path.exists(file_path):
                                    try:
                                        # Extract citation information
                                        citation, metadata = extract_citation_info(filename, file_path)
                                        
                                        if citation:
                                            # Make sure metadata is not None
                                            if metadata is None:
                                                metadata = {}
                                            formatted_citation = metadata.get("formatted_citation", citation)
                                            doi = metadata.get("doi")
                                            
                                            # Update the database
                                            cursor.execute("""
                                                UPDATE documents
                                                SET formatted_citation = %s, doi = %s
                                                WHERE id = %s
                                            """, (formatted_citation, doi, row['id']))
                                            conn.commit()
                                            
                                            logger.info(f"Updated PostgreSQL citation for {filename}: {formatted_citation}")
                                        else:
                                            logger.warning(f"Could not extract citation for {filename}")
                                    except Exception as e:
                                        logger.error(f"Error processing {filename}: {e}")
                        else:
                            logger.info("All PostgreSQL documents have citations")
            else:
                logger.error(f"Unknown database type: {DB_URL}")
        except Exception as e:
            logger.error(f"Error updating database records: {e}")
        
    except Exception as e:
        logger.error(f"Error updating vector store: {e}")
        # Print the traceback for better debugging
        import traceback
        traceback.print_exc()
        return False
        
    return True

if __name__ == "__main__":
    update_vector_store_citations()