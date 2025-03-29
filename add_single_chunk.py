"""
This script processes a single chunk from a document and adds it to the vector store.
It's designed to be run repeatedly to process all chunks incrementally.
"""
import os
import sys
import logging
import time
from app import app, db, Document, DocumentChunk
from utils.vector_store import VectorStore
from utils.openai_service import get_openai_embedding

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def add_next_chunk():
    """
    Find and process the next chunk that needs to be added to the vector store.
    
    Returns:
        bool: True if a chunk was processed, False if no more chunks to process
    """
    try:
        # Load the processing state
        doc_id, chunk_id = None, None
        if os.path.exists('chunk_state.txt'):
            with open('chunk_state.txt', 'r') as f:
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
                "source_type": document.file_type,
                "db_id": document.id,
                "filename": document.filename,
                "title": document.title or document.filename,
                "chunk_index": chunk.chunk_index,
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
                
            # For PDFs, add file path
            if document.file_type == "pdf" and document.file_path:
                metadata["file_path"] = document.file_path
                
            # For websites, add source URL
            if document.file_type == "website" and document.source_url:
                metadata["source_url"] = document.source_url
            
            # Get the vector store
            vector_store = VectorStore()
            
            # Generate embedding and add to vector store
            try:
                logger.info(f"Processing chunk {chunk.id} from document {document.id}: {document.filename}")
                embedding = get_openai_embedding(chunk.text_content)
                vector_store.add_embedding(chunk.text_content, embedding, metadata=metadata)
                # Explicitly save the vector store after adding the embedding
                vector_store.save()
                logger.info(f"Successfully added chunk {chunk.id} to vector store and saved")
            except Exception as e:
                logger.error(f"Error adding chunk {chunk.id} to vector store: {str(e)}")
                # Continue to the next chunk anyway
            
            # Find the next chunk to process
            next_chunk = DocumentChunk.query.filter(
                DocumentChunk.document_id == doc_id,
                DocumentChunk.chunk_index > chunk.chunk_index
            ).order_by(DocumentChunk.chunk_index).first()
            
            if next_chunk:
                # Update the state with the next chunk
                with open('chunk_state.txt', 'w') as f:
                    f.write(f"{doc_id},{next_chunk.id}")
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
                        with open('chunk_state.txt', 'w') as f:
                            f.write(f"{next_doc.id},{next_doc_chunk.id}")
                    else:
                        logger.warning(f"No chunks found for next document {next_doc.id}")
                        # Delete the state file to start fresh next time
                        if os.path.exists('chunk_state.txt'):
                            os.remove('chunk_state.txt')
                else:
                    logger.info("No more documents to process")
                    # Delete the state file to start fresh next time
                    if os.path.exists('chunk_state.txt'):
                        os.remove('chunk_state.txt')
            
            return True
    
    except Exception as e:
        logger.error(f"Error processing chunk: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Process the next chunk
    add_next_chunk()