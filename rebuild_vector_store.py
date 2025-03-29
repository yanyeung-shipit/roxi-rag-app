"""
This script rebuilds the vector store from scratch using the database as the source of truth.
It loads all documents from the database and creates new embeddings for them.
"""
import logging
import sys
import os
import psycopg2
import psycopg2.extras
from app import app, Document, DocumentChunk
from utils.vector_store import VectorStore
from utils.openai_service import get_openai_embedding, get_openai_embeddings_batch

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])

logger = logging.getLogger(__name__)

# Get DATABASE_URL from environment
DB_URL = os.environ.get("DATABASE_URL", "sqlite:///instance/app.db")

def rebuild_vector_store():
    """
    This script rebuilds the vector store from scratch using the database as the source of truth.
    It loads all documents from the database and creates new embeddings for them.
    """
    try:
        logger.info("Starting vector store rebuild from database...")
        
        # Create a new vector store
        # First, clear the existing vector store instead of using force_new
        vector_store = VectorStore()
        vector_store.clear()
        
        # Number of chunks to process in each batch
        BATCH_SIZE = 50
        
        with app.app_context():
            # Get total number of documents and chunks
            doc_count = Document.query.count()
            chunk_count = DocumentChunk.query.count()
            logger.info(f"Found {doc_count} documents with {chunk_count} total chunks in database")
            
            # Process all documents that have chunks
            documents = Document.query.filter(Document.chunks.any()).all()
            logger.info(f"Processing {len(documents)} documents with at least one chunk")
            
            total_processed = 0
            total_chunks = 0
            
            # Process each document
            for document in documents:
                try:
                    logger.info(f"Processing document {document.id}: {document.filename}")
                    
                    # Get all chunks for this document
                    chunks = document.chunks
                    total_chunks += len(chunks)
                    
                    # Process chunks in batches to avoid memory issues
                    for i in range(0, len(chunks), BATCH_SIZE):
                        batch = chunks[i:i+BATCH_SIZE]
                        
                        # Create metadata for document
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
                            
                        # Extract texts from chunks
                        texts = [chunk.text_content for chunk in batch]
                        
                        # Generate embeddings for all texts in batch
                        logger.info(f"Generating embeddings for {len(texts)} chunks...")
                        embeddings = get_openai_embeddings_batch(texts)
                        
                        # Add each chunk with its embedding to vector store
                        for j, chunk in enumerate(batch):
                            # Use the same base metadata but add chunk-specific info
                            chunk_metadata = metadata.copy()
                            chunk_metadata["chunk_index"] = chunk.chunk_index
                            if chunk.page_number is not None:
                                chunk_metadata["page_number"] = chunk.page_number
                                
                            # Add text and embedding to vector store
                            vector_store.add_embedding(
                                text=chunk.text_content,
                                embedding=embeddings[j],
                                metadata=chunk_metadata
                            )
                            
                        logger.info(f"Added batch of {len(batch)} chunks to vector store")
                    
                    total_processed += 1
                    if total_processed % 5 == 0:
                        logger.info(f"Progress: {total_processed}/{len(documents)} documents processed")
                        # Save vector store periodically
                        vector_store.save()
                        
                except Exception as doc_error:
                    logger.error(f"Error processing document {document.id}: {str(doc_error)}")
                    continue
            
            # Final save
            vector_store.save()
            logger.info(f"Vector store rebuild complete! Added {total_chunks} chunks from {total_processed} documents")
            
            return True
            
    except Exception as e:
        logger.error(f"Error rebuilding vector store: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    rebuild_vector_store()