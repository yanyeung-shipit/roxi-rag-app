"""
This script starts the vector store rebuild process and is intended to be run 
directly by the server to rebuild the vector store from the database.
"""
import os
import sys
import logging
import time
from flask import Flask
from app import app, db, Document, DocumentChunk
from utils.vector_store import VectorStore
from utils.openai_service import get_openai_embedding

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def add_chunks_to_vector_store(document_id):
    """
    Process a single document and add its chunks to the vector store.
    This is a smaller operation that can complete within the timeout limits.
    
    Args:
        document_id (int): The ID of the document to process
        
    Returns:
        tuple: (success, number of chunks processed)
    """
    try:
        with app.app_context():
            # Get the document
            document = Document.query.get(document_id)
            if not document:
                logger.error(f"Document with ID {document_id} not found")
                return False, 0
                
            # Skip if no chunks
            if not document.chunks:
                logger.info(f"Document {document_id} has no chunks, skipping")
                return True, 0
                
            # Get all chunks for this document
            chunks = document.chunks
            
            # Create base metadata for document
            metadata = {
                "source_type": document.file_type,
                "db_id": document.id,
                "filename": document.filename,
                "title": document.title or document.filename,
            }
            
            # Add citation information if available
            if document.formatted_citation:
                metadata["formatted_citation"] = document.formatted_citation
                metadata["citation"] = document.formatted_citation
                
            if document.doi:
                metadata["doi"] = document.doi
                
            # For PDFs, add file path
            if document.file_type == "pdf" and document.file_path:
                metadata["file_path"] = document.file_path
                
            # For websites, add source URL
            if document.file_type == "website" and document.source_url:
                metadata["source_url"] = document.source_url
                
            # Create vector store
            vector_store = VectorStore()
            
            # Process each chunk
            for chunk in chunks:
                try:
                    # Use the same base metadata but add chunk-specific info
                    chunk_metadata = metadata.copy()
                    chunk_metadata["chunk_index"] = chunk.chunk_index
                    if chunk.page_number is not None:
                        chunk_metadata["page_number"] = chunk.page_number
                    
                    # Add to vector store with pre-computed embedding
                    embedding = get_openai_embedding(chunk.text_content)
                    vector_store.add_embedding(chunk.text_content, embedding, metadata=chunk_metadata)
                    
                except Exception as e:
                    logger.error(f"Error processing chunk {chunk.id}: {str(e)}")
                    continue
            
            # Return success
            return True, len(chunks)
            
    except Exception as e:
        logger.error(f"Error processing document {document_id}: {str(e)}")
        return False, 0

def get_unprocessed_document_ids():
    """
    Get the IDs of all documents that have chunks but may not be in the vector store.
    
    Returns:
        list: List of document IDs
    """
    with app.app_context():
        # Get all documents that have at least one chunk
        documents = Document.query.filter(Document.chunks.any()).all()
        return [doc.id for doc in documents]

def get_next_document_id():
    """
    Get the ID of the next document to process.
    
    Returns:
        int or None: The ID of the next document, or None if no more documents
    """
    try:
        # Check if there's a file with the next document ID
        if os.path.exists('next_document_id.txt'):
            with open('next_document_id.txt', 'r') as f:
                next_id = int(f.read().strip())
            return next_id
        else:
            # Get the first document ID
            document_ids = get_unprocessed_document_ids()
            if document_ids:
                return document_ids[0]
            else:
                return None
    except Exception as e:
        logger.error(f"Error getting next document ID: {str(e)}")
        return None

def update_next_document_id(processed_id):
    """
    Update the next document ID to process.
    
    Args:
        processed_id (int): The ID of the document that was just processed
    """
    try:
        # Get all document IDs
        document_ids = get_unprocessed_document_ids()
        
        # Find the index of the processed ID
        if processed_id in document_ids:
            idx = document_ids.index(processed_id)
            # If there are more documents, set the next ID
            if idx + 1 < len(document_ids):
                next_id = document_ids[idx + 1]
                with open('next_document_id.txt', 'w') as f:
                    f.write(str(next_id))
            else:
                # No more documents, delete the file
                if os.path.exists('next_document_id.txt'):
                    os.remove('next_document_id.txt')
    except Exception as e:
        logger.error(f"Error updating next document ID: {str(e)}")

def main():
    """
    Main entry point to rebuild the vector store.
    
    This function processes one document at a time to ensure it 
    completes before the server times out.
    """
    start_time = time.time()
    
    # Get the next document ID to process
    document_id = get_next_document_id()
    if not document_id:
        logger.info("No more documents to process")
        return
        
    logger.info(f"Processing document ID: {document_id}")
    
    # Process the document
    success, chunk_count = add_chunks_to_vector_store(document_id)
    
    if success:
        logger.info(f"Successfully processed document ID {document_id} with {chunk_count} chunks")
        # Update the next document ID
        update_next_document_id(document_id)
    else:
        logger.error(f"Failed to process document ID {document_id}")
        
    end_time = time.time()
    logger.info(f"Run completed in {end_time - start_time:.2f} seconds")

if __name__ == "__main__":
    # Run the main function
    main()