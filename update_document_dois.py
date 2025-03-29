"""
This script updates documents in both the database and vector store
by extracting DOIs from document text and updating their metadata.
"""

import os
import logging
import pickle
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

from utils.doi_lookup import extract_doi_from_text, get_citation_from_doi
from models import Document, DocumentChunk, db
from app import app

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Vector store file path
VECTOR_STORE_PATH = "document_data.pkl"

def load_vector_store():
    """Load the vector store from disk."""
    if not Path(VECTOR_STORE_PATH).exists():
        logger.error(f"Vector store file not found at {VECTOR_STORE_PATH}")
        return None
    
    try:
        with open(VECTOR_STORE_PATH, "rb") as f:
            data = pickle.load(f)
            logger.info(f"Loaded vector store with {len(data['documents'])} documents")
            return data
    except Exception as e:
        logger.exception(f"Error loading vector store: {str(e)}")
        return None

def save_vector_store(data):
    """Save the vector store to disk."""
    try:
        # Create a backup first
        if Path(VECTOR_STORE_PATH).exists():
            backup_path = f"{VECTOR_STORE_PATH}.bak.{int(time.time())}"
            with open(VECTOR_STORE_PATH, "rb") as src:
                with open(backup_path, "wb") as dst:
                    dst.write(src.read())
            logger.info(f"Created backup of vector store at {backup_path}")
        
        # Save the updated vector store
        with open(VECTOR_STORE_PATH, "wb") as f:
            pickle.dump(data, f)
            logger.info(f"Saved vector store with {len(data['documents'])} documents")
        return True
    except Exception as e:
        logger.exception(f"Error saving vector store: {str(e)}")
        return False

def extract_doi_and_update_metadata(document_id: int, chunk_texts: List[str]) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    Extract DOI from document chunk texts and update metadata.
    
    Args:
        document_id (int): The document ID.
        chunk_texts (List[str]): List of document chunk texts.
        
    Returns:
        Tuple[bool, Optional[str], Optional[Dict[str, Any]]]: A tuple containing:
            - bool: True if a DOI was found and metadata was updated, False otherwise.
            - Optional[str]: The extracted DOI, or None if no DOI was found.
            - Optional[Dict[str, Any]]: The metadata from the DOI lookup, or None if no metadata was found.
    """
    for text in chunk_texts:
        doi = extract_doi_from_text(text)
        if doi:
            # Found a DOI, now try to get metadata
            success, metadata = get_citation_from_doi(doi)
            if success and metadata:
                logger.info(f"Successfully found DOI {doi} for document {document_id} with metadata: {metadata}")
                return True, doi, metadata
            else:
                logger.warning(f"Found DOI {doi} for document {document_id} but failed to get metadata")
                return False, doi, None
    
    logger.info(f"No DOI found for document {document_id}")
    return False, None, None

def update_document_dois_in_db():
    """Update DOIs for documents in the database."""
    with app.app_context():
        # Get all documents that don't have a DOI or formatted citation
        documents = Document.query.filter(
            (Document.doi.is_(None) | Document.formatted_citation.is_(None)) & 
            (Document.file_type == 'pdf')
        ).all()
        
        logger.info(f"Found {len(documents)} documents in the database to check for DOIs")
        
        updated_count = 0
        
        for doc in documents:
            # Gather all text chunks for this document
            chunks = DocumentChunk.query.filter_by(document_id=doc.id).order_by(DocumentChunk.chunk_index).all()
            
            if not chunks:
                logger.warning(f"No chunks found for document {doc.id} ({doc.filename})")
                continue
            
            # Extract text from chunks
            chunk_texts = [chunk.text_content for chunk in chunks]
            
            # Try to extract DOI and update metadata
            success, doi, metadata = extract_doi_and_update_metadata(doc.id, chunk_texts)
            
            if success and metadata:
                # Update document with DOI and metadata
                doc.doi = doi
                
                if "title" in metadata and metadata["title"]:
                    doc.title = metadata["title"]
                
                if "authors" in metadata and metadata["authors"]:
                    doc.authors = metadata["authors"]
                
                if "journal" in metadata and metadata["journal"]:
                    doc.journal = metadata["journal"]
                
                if "publication_year" in metadata and metadata["publication_year"]:
                    doc.publication_year = metadata["publication_year"]
                
                if "volume" in metadata and metadata["volume"]:
                    doc.volume = metadata["volume"]
                
                if "issue" in metadata and metadata["issue"]:
                    doc.issue = metadata["issue"]
                
                if "pages" in metadata and metadata["pages"]:
                    doc.pages = metadata["pages"]
                
                if "formatted_citation" in metadata and metadata["formatted_citation"]:
                    doc.formatted_citation = metadata["formatted_citation"]
                
                db.session.commit()
                updated_count += 1
                logger.info(f"Updated document {doc.id} ({doc.filename}) with DOI {doi}")
            elif doi:
                # We found a DOI but couldn't get metadata, still update the DOI
                doc.doi = doi
                db.session.commit()
                logger.info(f"Updated document {doc.id} ({doc.filename}) with DOI {doi} but no metadata")
        
        logger.info(f"Updated {updated_count} documents in the database with DOI metadata")
        return updated_count

def update_document_dois_in_vector_store(max_documents=100):
    """
    Update DOIs for documents in the vector store.
    
    Args:
        max_documents (int): Maximum number of documents to process for DOI extraction.
    """
    # Load the vector store
    data = load_vector_store()
    if not data:
        logger.error("Failed to load vector store")
        return 0
    
    documents = data.get("documents", {})
    logger.info(f"Loaded {len(documents)} documents from vector store")
    
    updated_count = 0
    documents_by_file_path = {}
    documents_without_doi = []
    
    # First, catalog documents by file_path to find those without DOIs
    for doc_id, doc in documents.items():
        if not isinstance(doc, dict):
            logger.warning(f"Document {doc_id} is not a dictionary, skipping")
            continue
            
        metadata = doc.get("metadata", {})
        file_path = metadata.get("file_path")
        
        if file_path:
            if file_path not in documents_by_file_path:
                documents_by_file_path[file_path] = []
            documents_by_file_path[file_path].append((doc_id, doc))
        
        # Check if the document has no DOI or formatted citation
        if metadata.get("file_type") == "pdf" and (
            "doi" not in metadata or not metadata["doi"] or
            "formatted_citation" not in metadata or not metadata["formatted_citation"]
        ):
            documents_without_doi.append((doc_id, doc))
    
    logger.info(f"Found {len(documents_without_doi)} documents without DOI in vector store")
    
    # Connect to the database to get updated metadata
    with app.app_context():
        # Get documents from the database with DOI and citation
        db_docs = Document.query.filter(
            Document.doi.isnot(None) & 
            Document.formatted_citation.isnot(None)
        ).all()
        
        logger.info(f"Found {len(db_docs)} documents with DOI and citation in database")
        
        # Create a mapping of file paths to database documents
        db_docs_by_file_path = {doc.file_path: doc for doc in db_docs if doc.file_path}
        
        # Update vector store documents with DB metadata (no need to limit this part)
        for file_path, docs in documents_by_file_path.items():
            if file_path in db_docs_by_file_path:
                db_doc = db_docs_by_file_path[file_path]
                
                # Skip if the DB document has no DOI or citation
                if not db_doc.doi or not db_doc.formatted_citation:
                    continue
                
                for doc_id, doc in docs:
                    metadata = doc.get("metadata", {})
                    
                    # Only update PDF documents
                    if metadata.get("file_type") != "pdf":
                        continue
                    
                    # Update metadata with database fields
                    metadata["doi"] = db_doc.doi
                    metadata["title"] = db_doc.title
                    metadata["authors"] = db_doc.authors
                    metadata["journal"] = db_doc.journal
                    metadata["publication_year"] = db_doc.publication_year
                    metadata["volume"] = db_doc.volume
                    metadata["issue"] = db_doc.issue
                    metadata["pages"] = db_doc.pages
                    metadata["formatted_citation"] = db_doc.formatted_citation
                    metadata["citation"] = db_doc.formatted_citation
                    
                    # Update the document metadata
                    documents[doc_id]["metadata"] = metadata
                    updated_count += 1
        
        # For documents still without DOI, try to extract from content (limit this part)
        docs_to_process = documents_without_doi[:max_documents]
        logger.info(f"Processing {len(docs_to_process)} out of {len(documents_without_doi)} documents for DOI extraction")
        
        for doc_id, doc in docs_to_process:
            metadata = doc.get("metadata", {})
            
            # Skip if this document actually does have a DOI (likely updated in the previous step)
            if "doi" in metadata and metadata["doi"]:
                continue
            
            # Only process PDF documents
            if metadata.get("file_type") != "pdf":
                continue
            
            # Try to extract DOI from the document text
            text = doc.get("text", "")
            if text:
                success, doi, doi_metadata = extract_doi_and_update_metadata(doc_id, [text])
                
                if success and doi_metadata:
                    # Update metadata with DOI lookup results
                    metadata["doi"] = doi
                    if "title" in doi_metadata and doi_metadata["title"]:
                        metadata["title"] = doi_metadata["title"]
                    if "authors" in doi_metadata and doi_metadata["authors"]:
                        metadata["authors"] = doi_metadata["authors"]
                    if "journal" in doi_metadata and doi_metadata["journal"]:
                        metadata["journal"] = doi_metadata["journal"]
                    if "publication_year" in doi_metadata and doi_metadata["publication_year"]:
                        metadata["publication_year"] = doi_metadata["publication_year"]
                    if "volume" in doi_metadata and doi_metadata["volume"]:
                        metadata["volume"] = doi_metadata["volume"]
                    if "issue" in doi_metadata and doi_metadata["issue"]:
                        metadata["issue"] = doi_metadata["issue"]
                    if "pages" in doi_metadata and doi_metadata["pages"]:
                        metadata["pages"] = doi_metadata["pages"]
                    if "formatted_citation" in doi_metadata and doi_metadata["formatted_citation"]:
                        metadata["formatted_citation"] = doi_metadata["formatted_citation"]
                        metadata["citation"] = doi_metadata["formatted_citation"]
                    
                    # Update the document metadata
                    documents[doc_id]["metadata"] = metadata
                    updated_count += 1
                    logger.info(f"Updated vector store document {doc_id} with DOI {doi}")
                elif doi:
                    # We found a DOI but couldn't get metadata
                    metadata["doi"] = doi
                    documents[doc_id]["metadata"] = metadata
                    logger.info(f"Updated vector store document {doc_id} with DOI {doi} but no metadata")
    
    # Save the updated vector store
    data["documents"] = documents
    if save_vector_store(data):
        total_processed = len(docs_to_process) if 'docs_to_process' in locals() else 0
        total_remaining = len(documents_without_doi) - total_processed
        
        logger.info(f"Updated and saved {updated_count} documents in the vector store")
        logger.info(f"Remaining documents without DOI to process: {total_remaining}")
        return updated_count
    
    logger.error("Failed to save vector store")
    return 0

def main():
    """Run the DOI update process for both database and vector store."""
    logger.info("Starting DOI update process")
    
    # Update DOIs in the database
    db_updated_count = update_document_dois_in_db()
    logger.info(f"Updated {db_updated_count} documents in the database")
    
    # Update DOIs in the vector store with a small limit to finish quickly
    vs_updated_count = update_document_dois_in_vector_store(max_documents=10)
    logger.info(f"Updated {vs_updated_count} documents in the vector store")
    
    logger.info("DOI update process completed")
    return db_updated_count, vs_updated_count

if __name__ == "__main__":
    main()