"""
This script processes a single chunk from a document and adds it to the vector store.
It's designed to be run repeatedly to process all chunks incrementally.
Version 2.0: Enhanced with better tracking and error handling.
"""
import os
import sys
import json
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, Union, Tuple
from app import app, db, Document, DocumentChunk
from utils.vector_store import VectorStore
from utils.openai_service import get_openai_embedding

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Path to the state file
STATE_FILE_PATH = 'chunk_state.txt'
ERROR_LOG_PATH = 'logs/chunk_processing_errors.log'

def setup_log_directory():
    """Create the log directory if it doesn't exist."""
    log_dir = os.path.dirname(ERROR_LOG_PATH)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

def log_processing_error(chunk_id: int, document_id: int, error_message: str):
    """
    Log an error during chunk processing.
    
    Args:
        chunk_id (int): The ID of the chunk being processed
        document_id (int): The ID of the document containing the chunk
        error_message (str): The error message
    """
    setup_log_directory()
    
    error_entry = {
        "timestamp": datetime.now().isoformat(),
        "chunk_id": chunk_id,
        "document_id": document_id,
        "error": error_message
    }
    
    with open(ERROR_LOG_PATH, "a") as f:
        f.write(json.dumps(error_entry) + "\n")

def add_next_chunk() -> Union[Dict[str, Any], bool]:
    """
    Find and process the next chunk that needs to be added to the vector store.
    
    Returns:
        dict or bool: Dictionary with processing results if successful, False if error or no more chunks
    """
    try:
        # Load the processing state
        doc_id, chunk_id = None, None
        if os.path.exists(STATE_FILE_PATH):
            with open(STATE_FILE_PATH, 'r') as f:
                state = f.read().strip().split(',')
                if len(state) == 2:
                    doc_id, chunk_id = int(state[0]), int(state[1])
        
        with app.app_context():
            # If no state, find the first document with chunks
            if doc_id is None:
                document = Document.query.filter(Document.chunks.any()).first()
                if not document:
                    logger.info("No documents with chunks found")
                    return False
                doc_id = document.id
                # Get the first chunk from this document
                chunk = DocumentChunk.query.filter_by(document_id=doc_id).order_by(DocumentChunk.chunk_index).first()
                if not chunk:
                    logger.info(f"No chunks found for document {doc_id}")
                    return False
                chunk_id = chunk.id
            else:
                # Get the current chunk
                chunk = DocumentChunk.query.get(chunk_id)
                if not chunk:
                    logger.error(f"Chunk with ID {chunk_id} not found")
                    return False
            
            # Get the document
            document = Document.query.get(chunk.document_id)
            if not document:
                logger.error(f"Document with ID {chunk.document_id} not found")
                return False
            
            # Create metadata for this chunk
            metadata = {
                "document_id": document.id,  # Store actual document_id for direct lookup
                "source_type": document.file_type,
                "db_id": document.id,  # Legacy field, keep for backward compatibility
                "filename": document.filename,
                "title": document.title or document.filename,
                "chunk_index": chunk.chunk_index,
                "chunk_id": chunk.id  # Store actual chunk_id for tracking
            }
            
            # Add page number if available
            if chunk.page_number is not None:
                metadata["page_number"] = chunk.page_number
            
            # Add citation information if available
            if document.formatted_citation:
                metadata["formatted_citation"] = document.formatted_citation
                metadata["citation"] = document.formatted_citation
                
            if document.doi:
                metadata["doi"] = document.doi
                
            if document.authors:
                metadata["authors"] = document.authors
                
            if document.journal:
                metadata["journal"] = document.journal
                
            if document.publication_year:
                metadata["publication_year"] = document.publication_year
                
            # For PDFs, add file path
            if document.file_type == "pdf" and document.file_path:
                metadata["file_path"] = document.file_path
                
            # For websites, add source URL
            if document.file_type == "website" and document.source_url:
                metadata["source_url"] = document.source_url
            
            # Get the vector store
            vector_store = VectorStore()
            
            # Track success and error info
            success = False
            error_message = None
            
            # Generate embedding and add to vector store
            try:
                start_time = time.time()
                logger.info(f"Processing chunk {chunk.id} from document {document.id}: {document.filename}")
                
                # Generate the embedding
                embedding = get_openai_embedding(chunk.text_content)
                
                # Add to vector store
                vector_store.add_embedding(chunk.text_content, embedding, metadata=metadata)
                
                # Explicitly save the vector store after adding the embedding
                vector_store.save()
                
                processing_time = time.time() - start_time
                logger.info(f"Successfully added chunk {chunk.id} to vector store in {processing_time:.2f}s")
                
                success = True
                
            except Exception as e:
                error_message = str(e)
                logger.error(f"Error adding chunk {chunk.id} to vector store: {error_message}")
                log_processing_error(chunk.id, document.id, error_message)
                # Continue to the next chunk anyway
            
            # Create result information about the current chunk
            result_info = {
                "success": success,
                "chunk_id": chunk.id,
                "document_id": document.id,
                "filename": document.filename,
                "chunk_index": chunk.chunk_index,
                "error": error_message
            }
            
            # Find the next chunk to process
            next_chunk = DocumentChunk.query.filter(
                DocumentChunk.document_id == doc_id,
                DocumentChunk.chunk_index > chunk.chunk_index
            ).order_by(DocumentChunk.chunk_index).first()
            
            if next_chunk:
                # Update the state with the next chunk
                with open(STATE_FILE_PATH, 'w') as f:
                    f.write(f"{doc_id},{next_chunk.id}")
                
                # Add next chunk info to result
                result_info["next_chunk_id"] = next_chunk.id
                result_info["next_chunk_index"] = next_chunk.chunk_index
                
            else:
                # Move to the next document
                next_doc = Document.query.filter(
                    Document.id > doc_id,
                    Document.chunks.any()
                ).order_by(Document.id).first()
                
                if next_doc:
                    # Get the first chunk from the next document
                    next_doc_chunk = DocumentChunk.query.filter_by(
                        document_id=next_doc.id
                    ).order_by(DocumentChunk.chunk_index).first()
                    
                    if next_doc_chunk:
                        # Update the state with the next document and chunk
                        with open(STATE_FILE_PATH, 'w') as f:
                            f.write(f"{next_doc.id},{next_doc_chunk.id}")
                        
                        # Add next document and chunk info to result
                        result_info["next_document_id"] = next_doc.id
                        result_info["next_chunk_id"] = next_doc_chunk.id
                        result_info["next_chunk_index"] = next_doc_chunk.chunk_index
                        
                    else:
                        logger.warning(f"No chunks found for next document {next_doc.id}")
                        # Delete the state file to start fresh next time
                        if os.path.exists(STATE_FILE_PATH):
                            os.remove(STATE_FILE_PATH)
                            
                        # Indicate no next chunk in result
                        result_info["next_document_id"] = next_doc.id
                        result_info["next_chunk_id"] = None
                        
                else:
                    logger.info("No more documents to process")
                    # Delete the state file to start fresh next time
                    if os.path.exists(STATE_FILE_PATH):
                        os.remove(STATE_FILE_PATH)
                    
                    # Indicate processing complete in result
                    result_info["processing_complete"] = True
            
            return result_info
    
    except Exception as e:
        logger.error(f"Error processing chunk: {str(e)}")
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(error_traceback)
        
        # Create error result
        return {
            "success": False,
            "error": str(e),
            "traceback": error_traceback
        }

if __name__ == "__main__":
    # Process the next chunk
    result = add_next_chunk()
    
    # Print result summary
    if isinstance(result, dict):
        if result.get("success"):
            print(f"Successfully processed chunk {result.get('chunk_id')}")
        else:
            print(f"Failed to process chunk: {result.get('error')}")
    else:
        print("No more chunks to process")