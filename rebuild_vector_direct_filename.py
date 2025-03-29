import os
import re
import logging
import sys
import pickle
import psycopg2
import psycopg2.extras
from collections import defaultdict

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])

logger = logging.getLogger(__name__)

def rebuild_vector_citations_by_filename():
    """
    This script specifically focuses on matching database entries to vector store entries
    by filename pattern only, with more aggressive matching.
    
    It directly looks for partial filename matches, accounting for the fact that the vector store
    might have stripped off timestamps, extensions, or other parts of the filename.
    """
    try:
        DB_URL = os.environ.get("DATABASE_URL", "sqlite:///instance/app.db")
        
        # Load the vector store data
        logger.info("Loading vector store data from document_data.pkl")
        
        # Create a backup before making changes
        backup_name = f"document_data.pkl.bak.rebuild.{int(os.path.getmtime('document_data.pkl'))}"
        logger.info(f"Creating backup at {backup_name}")
        with open("document_data.pkl", "rb") as f_src:
            with open(backup_name, "wb") as f_dst:
                f_dst.write(f_src.read())
        
        with open("document_data.pkl", "rb") as f:
            vector_store_data = pickle.load(f)
        
        # Get documents from vector store
        documents = vector_store_data.get("documents", {})
        logger.info(f"Vector store has {len(documents)} total documents")
        
        # Count PDF documents
        pdf_docs_count = 0
        for doc_id, doc_data in documents.items():
            metadata = doc_data.get("metadata", {})
            if metadata.get("source_type") == "pdf":
                pdf_docs_count += 1
        
        logger.info(f"Vector store has {pdf_docs_count} documents with source_type='pdf'")
        
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
                    
                    # For each database document, try to find corresponding vector store entries
                    db_matches = 0
                    for row in rows:
                        db_id = row["id"]
                        filename = row["filename"]
                        title = row["title"]
                        formatted_citation = row["formatted_citation"]
                        doi = row["doi"]
                        
                        if not filename:
                            logger.warning(f"Skipping database document {db_id} with no filename")
                            continue
                        
                        # Get filename base without extension
                        filename_base = os.path.splitext(filename)[0]
                        
                        # Strip timestamp pattern from beginning if present
                        filename_base_stripped = re.sub(r'^\d{8}_\d{6}_', '', filename_base)
                        filename_base_stripped = re.sub(r'^\d{8}_', '', filename_base_stripped)
                        
                        # Found document IDs
                        found_ids = set()
                        
                        # Go through vector store documents and try to match by filename pattern
                        for doc_id, doc_data in documents.items():
                            metadata = doc_data.get("metadata", {})
                            vs_filename = metadata.get("filename", "")
                            vs_title = metadata.get("title", "")
                            
                            # Skip if not a PDF
                            if metadata.get("source_type") != "pdf":
                                continue
                            
                            # Exact filename match
                            if vs_filename and vs_filename == filename:
                                found_ids.add(doc_id)
                                logger.info(f"Matched document {db_id} by exact filename: {filename}")
                                continue
                                
                            # Check if vector store filename contains our filename
                            if vs_filename and filename_base in vs_filename:
                                found_ids.add(doc_id)
                                logger.info(f"Matched document {db_id} by filename inclusion: {filename_base} in {vs_filename}")
                                continue
                            
                            # Check if our filename contains vector store filename
                            if vs_filename and vs_filename in filename:
                                found_ids.add(doc_id)
                                logger.info(f"Matched document {db_id} by filename inclusion (reverse): {vs_filename} in {filename}")
                                continue
                            
                            # Check for stripped timestamp filename match
                            if vs_filename and filename_base_stripped in vs_filename:
                                found_ids.add(doc_id)
                                logger.info(f"Matched document {db_id} by stripped filename: {filename_base_stripped} in {vs_filename}")
                                continue
                            
                            # Check for keyword match in the title
                            keywords = filename_base.replace("_", " ").replace("-", " ").lower().split()
                            keywords = [k for k in keywords if len(k) > 3]  # Filter out short words
                            
                            vs_title_lower = vs_title.lower() if vs_title else ""
                            
                            if vs_title_lower and keywords:
                                matching_keywords = [k for k in keywords if k in vs_title_lower]
                                if len(matching_keywords) >= 2:  # At least 2 keyword matches
                                    found_ids.add(doc_id)
                                    logger.info(f"Matched document {db_id} by keywords in title: {', '.join(matching_keywords)}")
                                    continue
                        
                        # Now update all found documents with database metadata
                        if found_ids:
                            db_matches += 1
                            logger.info(f"Updating {len(found_ids)} vector store entries for document {db_id} ({filename})")
                            
                            for doc_id in found_ids:
                                # Ensure metadata dict exists
                                if "metadata" not in documents[doc_id]:
                                    documents[doc_id]["metadata"] = {}
                                
                                metadata = documents[doc_id]["metadata"]
                                
                                # Mark as PDF if it's not already
                                metadata["source_type"] = "pdf"
                                
                                # Update metadata with database values
                                if title:
                                    metadata["title"] = title
                                if formatted_citation:
                                    metadata["citation"] = formatted_citation
                                    metadata["formatted_citation"] = formatted_citation
                                if doi:
                                    metadata["doi"] = doi
                                if filename:
                                    metadata["filename"] = filename
                                
                                # Make sure we have reference to the database ID
                                metadata["db_id"] = db_id
                                
                                # Log the update details
                                logger.info(f"Updated document {doc_id} with metadata: title='{title}', citation='{formatted_citation[:50] if formatted_citation else ''}'")
                        else:
                            logger.warning(f"No vector store matches found for database document {db_id} ({filename})")
                    
                    logger.info(f"Updated {db_matches} out of {len(rows)} database documents in vector store")
                    
                    # Save the updated vector store
                    logger.info("Saving updated vector store")
                    with open("document_data.pkl", "wb") as f:
                        pickle.dump(vector_store_data, f)
                    
                    logger.info("Vector store updated successfully!")
        else:
            logger.error("Only PostgreSQL database is supported")
            return False
                
        return True
        
    except Exception as e:
        logger.error(f"Error rebuilding vector citations: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    rebuild_vector_citations_by_filename()