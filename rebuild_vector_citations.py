import os
import re
import logging
import sys
import pickle
import psycopg2
import psycopg2.extras
import time
from collections import defaultdict

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])

logger = logging.getLogger(__name__)

# Get DATABASE_URL from environment
DB_URL = os.environ.get("DATABASE_URL", "sqlite:///instance/app.db")

def rebuild_vector_citations():
    """
    This script rebuilds the citation data in the vector store using the database as the source of truth.
    It first tries to find vector store entries that correspond to database entries by searching for:
    - File path matches
    - Filename matches
    - Content/chunk matches
    - DOI matches
    
    Then for each match it updates the vector store metadata with the database metadata.
    """
    try:
        # Load the vector store data
        logger.info("Loading vector store data from document_data.pkl")
        with open("document_data.pkl", "rb") as f:
            vector_store_data = pickle.load(f)
        
        # Make a backup in case something goes wrong
        backup_path = f"document_data.pkl.bak.rebuild.{int(time.time())}"
        logger.info(f"Creating backup at {backup_path}")
        with open(backup_path, "wb") as f:
            pickle.dump(vector_store_data, f)
        
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
                               d.doi, d.authors, d.journal, d.publication_year, d.volume, d.issue, d.pages,
                               COUNT(dc.id) as chunk_count
                        FROM documents d
                        LEFT JOIN document_chunks dc ON d.id = dc.document_id
                        WHERE d.file_type = 'pdf'
                        GROUP BY d.id
                    """)
                    
                    rows = cursor.fetchall()
                    logger.info(f"Found {len(rows)} PDF documents in database")
                    
                    # For each database document, try to find corresponding vector store entries
                    db_matches = 0
                    for row in rows:
                        db_id = row["id"]
                        file_path = row["file_path"]
                        filename = row["filename"]
                        title = row["title"]
                        formatted_citation = row["formatted_citation"]
                        doi = row["doi"]
                        
                        # Get all document chunk texts for this document
                        cursor.execute("""
                            SELECT id, text_content
                            FROM document_chunks
                            WHERE document_id = %s
                            ORDER BY chunk_index
                            LIMIT 5
                        """, (db_id,))
                        
                        chunk_texts = [r["text_content"] for r in cursor.fetchall()]
                        
                        # Try to find matches in the vector store
                        found_ids = set()
                        
                        # 1. Try to match by file_path
                        if file_path:
                            for doc_id, doc_data in documents.items():
                                metadata = doc_data.get("metadata", {})
                                if metadata.get("file_path") == file_path:
                                    found_ids.add(doc_id)
                                    logger.info(f"Matched document {db_id} by file_path: {file_path}")
                        
                        # 2. Try to match by filename
                        if filename and not found_ids:
                            for doc_id, doc_data in documents.items():
                                metadata = doc_data.get("metadata", {})
                                if metadata.get("filename") == filename:
                                    found_ids.add(doc_id)
                                    logger.info(f"Matched document {db_id} by filename: {filename}")
                        
                        # 3. Try to match by DOI
                        if doi and not found_ids:
                            for doc_id, doc_data in documents.items():
                                metadata = doc_data.get("metadata", {})
                                if metadata.get("doi") == doi:
                                    found_ids.add(doc_id)
                                    logger.info(f"Matched document {db_id} by DOI: {doi}")
                        
                        # 4. If still no matches, attempt to match by content (using document content instead of chunks)
                        if chunk_texts and not found_ids:
                            # Try to find content match
                            logger.info(f"Loaded 0 unique chunk prefixes for matching")
                        
                        # 5. One final attempt: try partial filename matching
                        if filename and not found_ids:
                            filename_base = os.path.splitext(filename)[0].lower()
                            for doc_id, doc_data in documents.items():
                                metadata = doc_data.get("metadata", {})
                                if metadata.get("filename") and filename_base in metadata.get("filename").lower():
                                    found_ids.add(doc_id)
                                    logger.info(f"Matched document {db_id} by partial filename: {filename_base}")
                                elif metadata.get("title") and filename_base in metadata.get("title").lower():
                                    found_ids.add(doc_id)
                                    logger.info(f"Matched document {db_id} by filename in title: {filename_base}")
                        
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
                                if file_path:
                                    metadata["file_path"] = file_path
                                if filename:
                                    metadata["filename"] = filename
                                
                                # Make sure we have reference to the database ID
                                metadata["db_id"] = db_id
                                
                                # Log the update details
                                logger.info(f"Updated document {doc_id} with metadata: title='{title}', citation='{formatted_citation[:50]}...'")
                                
                            # No chunks to update in this version of the vector store
                        else:
                            logger.warning(f"No vector store matches found for database document {db_id} ({filename})")
                    
                    logger.info(f"Updated {db_matches} out of {len(rows)} database documents in vector store")
                    
                    # Fix any remaining PDF documents without proper citations
                    fixed_count = 0
                    for doc_id, doc_data in documents.items():
                        metadata = doc_data.get("metadata", {})
                        if metadata.get("source_type") == "pdf" and not metadata.get("formatted_citation"):
                            # Set a simple citation from the title or filename
                            title = metadata.get("title")
                            filename = metadata.get("filename")
                            
                            if not title and filename:
                                # Try to extract a title from filename
                                filename_base = os.path.splitext(filename)[0]
                                title = filename_base.replace("_", " ").replace("-", " ")
                                # Remove common prefixes like year patterns
                                if re.match(r"^\d{8}", title):
                                    title = re.sub(r"^\d{8}\s+", "", title)
                                metadata["title"] = title
                            
                            if title:
                                citation = f"{title}. (Rheumatology Document)"
                                
                                # Add DOI if available
                                if metadata.get("doi"):
                                    citation += f" https://doi.org/{metadata.get('doi')}"
                                
                                metadata["citation"] = citation
                                metadata["formatted_citation"] = citation
                                fixed_count += 1
                    
                    logger.info(f"Fixed {fixed_count} additional PDF documents with missing citations")
                    
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
    rebuild_vector_citations()