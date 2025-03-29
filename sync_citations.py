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
        
        # Initialize updated_count outside of the conditional
        updated_count = 0
        
        # Get citations from database
        logger.info("Connecting to database to get citations")
        if DB_URL.startswith("postgresql://"):
            # Connect to PostgreSQL
            with psycopg2.connect(DB_URL) as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("""
                        SELECT id, file_path, filename, title, formatted_citation, doi, authors, journal, publication_year, volume, issue, pages
                        FROM documents
                        WHERE file_type = 'pdf'
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
                        title = row["title"] or "Unnamed PDF"
                        authors = row["authors"]
                        journal = row["journal"]
                        publication_year = row["publication_year"]
                        volume = row["volume"]
                        issue = row["issue"]
                        pages = row["pages"]
                        
                        # If no citation exists, create one using the metadata
                        if not citation:
                            # Try to generate a formatted citation based on academic paper metadata
                            if authors and journal and publication_year:
                                # Format authors (e.g., "Smith, J., Jones, A.B.")
                                citation = f"{authors}. ({publication_year}). {title}."
                                
                                # Add journal info if available
                                if journal:
                                    citation += f" {journal}"
                                    
                                    # Add volume and issue if available
                                    if volume:
                                        citation += f", {volume}"
                                        if issue:
                                            citation += f"({issue})"
                                    
                                    # Add pages if available
                                    if pages:
                                        citation += f", {pages}"
                                
                                # Add DOI if available
                                if doi:
                                    citation += f". https://doi.org/{doi}"
                            else:
                                # Create a simple citation with the title
                                citation = f"{title}. (Rheumatology Document)"
                                
                                # Add DOI if available
                                if doi:
                                    citation += f" https://doi.org/{doi}"
                        
                        # Skip entries that still don't have a citation or file path
                        if not file_path:
                            continue
                            
                        filename = row["filename"]
                        
                        # Look for documents with this file_path or matching filename
                        for doc_id, doc_data in documents.items():
                            metadata = doc_data.get("metadata", {})
                            
                            # Try different ways to match the document
                            matched = False
                            
                            # Check if we're dealing with a PDF source type or unknown source type
                            is_pdf_or_unknown = (
                                metadata.get("source_type") == "pdf" or 
                                metadata.get("source_type") == "unknown" or 
                                not metadata.get("source_type")
                            )
                            
                            # Match by file_path if present
                            if is_pdf_or_unknown and metadata.get("file_path") == file_path:
                                matched = True
                                # Set proper source_type if it was unknown or missing
                                if metadata.get("source_type") != "pdf":
                                    metadata["source_type"] = "pdf"
                                    logger.info(f"Fixed source_type for document: {filename}")
                            
                            # Match by filename if present
                            elif is_pdf_or_unknown and metadata.get("filename") == filename:
                                matched = True
                                # Set proper source_type if it was unknown or missing
                                if metadata.get("source_type") != "pdf":
                                    metadata["source_type"] = "pdf"
                                    logger.info(f"Fixed source_type for document: {filename}")
                            
                            # Match by title if present (assuming filename can be part of the title)
                            elif is_pdf_or_unknown and filename and metadata.get("title") and filename in metadata.get("title"):
                                matched = True
                                # Set proper source_type if it was unknown or missing
                                if metadata.get("source_type") != "pdf":
                                    metadata["source_type"] = "pdf"
                                    logger.info(f"Fixed source_type for document: {filename}")
                                    
                            # Try to match by extracted filename from title
                            elif is_pdf_or_unknown and filename and metadata.get("title"):
                                # Extract filename without extension and compare with title
                                filename_base = os.path.splitext(filename)[0]
                                if filename_base in metadata.get("title"):
                                    matched = True
                                    # Set proper source_type if it was unknown or missing
                                    if metadata.get("source_type") != "pdf":
                                        metadata["source_type"] = "pdf"
                                        logger.info(f"Fixed source_type for document: {filename}")
                                        
                            # Match by document title if that's all we have
                            elif is_pdf_or_unknown and title and metadata.get("title") and title == metadata.get("title"):
                                matched = True
                                # Set proper source_type if it was unknown or missing
                                if metadata.get("source_type") != "pdf":
                                    metadata["source_type"] = "pdf"
                                    logger.info(f"Fixed source_type for document: {filename}")
                                
                            if matched:
                                # Update citation
                                metadata["formatted_citation"] = citation
                                metadata["citation"] = citation
                                if doi:
                                    metadata["doi"] = doi
                                updated_count += 1
                                logger.info(f"Updated citation for document: {filename}")
        
        logger.info(f"Updated {updated_count} documents in vector store")
        
        # Final pass: Fix any remaining PDF documents without proper citations
        # This handles documents that didn't match with any database entries
        pdf_docs_fixed = 0
        
        for doc_id, doc_data in vector_store_data.get("documents", {}).items():
            metadata = doc_data.get("metadata", {})
            
            # Check if it's a PDF source type (or should be)
            if (metadata.get("source_type") == "pdf" or 
                metadata.get("source_type") == "unknown" or 
                not metadata.get("source_type")):
                
                # Check if it has a title but no proper citation
                if (metadata.get("title") and 
                    (not metadata.get("citation") or 
                     not metadata.get("formatted_citation") or
                     "Unnamed PDF" in metadata.get("citation", "") or
                     "Unnamed PDF" in metadata.get("formatted_citation", ""))):
                    
                    # Set source_type to PDF if it's not already
                    if metadata.get("source_type") != "pdf":
                        metadata["source_type"] = "pdf"
                    
                    # Create a better citation using the title
                    title = metadata.get("title")
                    citation = f"{title}. (Rheumatology Document)"
                    
                    # Add DOI if available
                    if metadata.get("doi"):
                        citation += f" https://doi.org/{metadata.get('doi')}"
                    
                    metadata["citation"] = citation
                    metadata["formatted_citation"] = citation
                    
                    pdf_docs_fixed += 1
                    logger.info(f"Fixed citation for document with ID {doc_id}: {title}")
        
        logger.info(f"Fixed {pdf_docs_fixed} additional PDF documents with missing or invalid citations")
                
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