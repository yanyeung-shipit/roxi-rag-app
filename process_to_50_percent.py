#!/usr/bin/env python3
"""
Process chunks until reaching a target percentage of total chunks.
This script handles the process in batches for efficiency.

Usage:
    python process_to_50_percent.py [--batch-size=10] [--target-percentage=50.0]
"""

import os
import sys
import time
import logging
import datetime
import argparse
from typing import Dict, Any, List, Set

# Parse command line arguments
parser = argparse.ArgumentParser(description='Process chunks to target percentage')
parser.add_argument('--batch-size', type=int, default=10, help='Number of chunks to process per batch')
parser.add_argument('--target-percentage', type=float, default=50.0, help='Target percentage of chunks to process')
args = parser.parse_args()

# Make sure the logs directory exists
os.makedirs("logs", exist_ok=True)

# Configure logging
log_filename = f"logs/process_to_50_percent_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app context
from app import app, db
from models import DocumentChunk
from utils.vector_store import VectorStore

# Constants
TARGET_PERCENTAGE = args.target_percentage
BATCH_SIZE = args.batch_size
MAX_BATCHES = 1000  # Increased safety limit for longer runs

def get_progress():
    """Get current progress of vector store rebuilding."""
    with app.app_context():
        # Get total chunks in database
        total_chunks = db.session.query(DocumentChunk).count()
        
        try:
            # Get processed chunks from vector store
            vector_store = VectorStore()
            
            # Force load if vector store is in sleep mode
            if not hasattr(vector_store, 'documents') or vector_store.documents is None:
                logger.info("Vector store is in sleep mode, loading from disk")
                vector_store.load()
                
            processed_chunks = len(vector_store.documents)
        except Exception as e:
            logger.error(f"Error getting processed chunks: {str(e)}")
            # Fallback to a safer method by counting the documents in the vector store file
            try:
                import pickle
                with open("document_data.pkl", "rb") as f:
                    documents = pickle.load(f)
                processed_chunks = len(documents)
                logger.info(f"Fallback method found {processed_chunks} processed chunks")
            except Exception as fallback_error:
                logger.error(f"Fallback method failed: {str(fallback_error)}")
                processed_chunks = 0
        
        # Calculate percentage
        percentage = round((processed_chunks / total_chunks) * 100, 1) if total_chunks > 0 else 0
        
        return {
            "total_chunks": total_chunks,
            "processed_chunks": processed_chunks,
            "percentage": percentage,
            "remaining_chunks": total_chunks - processed_chunks
        }

def get_unprocessed_chunks(batch_size):
    """Get a batch of unprocessed chunks."""
    try:
        # Initialize vector store
        vector_store = VectorStore()
        
        # Make sure vector store is loaded
        if not hasattr(vector_store, 'documents') or vector_store.documents is None:
            logger.info("Vector store is in sleep mode, loading from disk for chunk ID retrieval")
            vector_store.load()
            
        # Get processed chunk IDs safely
        try:
            processed_ids = vector_store.get_processed_chunk_ids()
            if not processed_ids:
                logger.warning("No processed IDs found, using utils.get_processed_chunks as fallback")
                from utils.get_processed_chunks import get_processed_chunk_ids
                processed_ids = get_processed_chunk_ids()
        except Exception as e:
            logger.error(f"Error getting processed chunk IDs: {str(e)}")
            processed_ids = []
            
        # Log the number of processed IDs found
        logger.info(f"Found {len(processed_ids)} processed chunk IDs")
        
        with app.app_context():
            # Get a sample of unprocessed chunks
            if processed_ids:
                # Use join to eagerly load document relationship
                chunks = db.session.query(DocumentChunk).options(
                    db.joinedload(DocumentChunk.document)
                ).filter(
                    ~DocumentChunk.id.in_(processed_ids)
                ).order_by(DocumentChunk.id).limit(batch_size).all()
            else:
                # If we couldn't get processed IDs, just get the first chunks
                chunks = db.session.query(DocumentChunk).options(
                    db.joinedload(DocumentChunk.document)
                ).order_by(DocumentChunk.id).limit(batch_size).all()
            
            logger.info(f"Retrieved {len(chunks)} unprocessed chunks")
            return chunks
    except Exception as e:
        logger.error(f"Error getting unprocessed chunks: {str(e)}")
        return []

def process_chunk(chunk, vector_store):
    """Process a single chunk and add it to vector store."""
    try:
        # Create safe version of metadata
        chunk_id = chunk.id
        document_id = chunk.document_id
        chunk_index = chunk.chunk_index
        text_content = chunk.text_content
        
        # Safe document properties
        document_filename = ""
        document_title = ""
        formatted_citation = None
        document_doi = None
        
        # Extract document properties safely
        if hasattr(chunk, 'document') and chunk.document:
            document = chunk.document
            document_filename = document.filename or ""
            document_title = document.title or ""
            
            if hasattr(document, 'formatted_citation'):
                formatted_citation = document.formatted_citation
                
            if hasattr(document, 'doi'):
                document_doi = document.doi
        
        # Create metadata
        metadata = {
            "chunk_id": chunk_id,
            "db_id": chunk_id,  # Include both for compatibility
            "document_id": document_id,
            "source_type": "pdf",  # Default value
            "chunk_index": chunk_index,
            "filename": document_filename,
            "title": document_title
        }
        
        # Add citation information if available
        if formatted_citation:
            metadata["citation"] = formatted_citation
        if document_doi:
            metadata["doi"] = document_doi
        
        # Add to vector store
        vector_store.add_text(text_content, metadata=metadata)
        
        return True
    except Exception as e:
        logger.error(f"Error processing chunk {chunk.id}: {str(e)}")
        return False

def main():
    """Main function to process chunks until target percentage."""
    try:
        logger.info("Initializing vector store")
        vector_store = VectorStore()
        
        # Get initial progress
        logger.info("Calculating initial progress")
        progress = get_progress()
        logger.info(f"Starting batch processing to reach {TARGET_PERCENTAGE}%")
        logger.info(f"Initial progress: {progress['percentage']}% "
                   f"({progress['processed_chunks']}/{progress['total_chunks']} chunks)")
        
        # Process in batches until target reached
        batches_processed = 0
        chunks_processed = 0
        consecutive_failures = 0
        max_consecutive_failures = 3
        
        while progress["percentage"] < TARGET_PERCENTAGE and batches_processed < MAX_BATCHES:
            try:
                # Get next batch
                logger.info(f"Fetching batch {batches_processed + 1}")
                chunks = get_unprocessed_chunks(BATCH_SIZE)
                
                if not chunks:
                    logger.info("No more chunks to process")
                    break
                
                # Process the batch
                logger.info(f"Processing batch {batches_processed + 1} with {len(chunks)} chunks")
                batch_success = 0
                
                for chunk in chunks:
                    try:
                        logger.info(f"Processing chunk {chunk.id}")
                        success = process_chunk(chunk, vector_store)
                        
                        if success:
                            batch_success += 1
                            chunks_processed += 1
                            consecutive_failures = 0
                            logger.info(f"Successfully processed chunk {chunk.id}")
                        else:
                            logger.error(f"Failed to process chunk {chunk.id}")
                            consecutive_failures += 1
                    except Exception as e:
                        logger.error(f"Error processing chunk {chunk.id}: {str(e)}")
                        consecutive_failures += 1
                        
                    # If too many consecutive failures, save and take a break
                    if consecutive_failures >= max_consecutive_failures:
                        logger.warning(f"Too many consecutive failures ({consecutive_failures}), saving and pausing")
                        vector_store.save()
                        logger.info("Vector store saved during error recovery")
                        time.sleep(5)  # Take a short break
                        consecutive_failures = 0
                
                # Save vector store after each batch
                logger.info("Saving vector store")
                vector_store.save()
                logger.info(f"Saved vector store after processing batch {batches_processed + 1}")
                
                # Update progress
                batches_processed += 1
                progress = get_progress()
                
                # Log progress
                logger.info(f"Batch {batches_processed} completed: "
                          f"{batch_success}/{len(chunks)} chunks successful")
                logger.info(f"Progress: {progress['percentage']}% "
                          f"({progress['processed_chunks']}/{progress['total_chunks']} chunks)")
                
                # Check if target reached
                if progress["percentage"] >= TARGET_PERCENTAGE:
                    logger.info(f"Target percentage of {TARGET_PERCENTAGE}% reached!")
                    break
                    
                # Short pause between batches to prevent API rate limits
                time.sleep(1)
                
            except Exception as batch_error:
                logger.error(f"Error processing batch: {str(batch_error)}")
                time.sleep(5)  # Take a break before trying the next batch
        
        # Final progress
        progress = get_progress()
        logger.info(f"Processing completed")
        logger.info(f"Final progress: {progress['percentage']}% "
                   f"({progress['processed_chunks']}/{progress['total_chunks']} chunks)")
        logger.info(f"Processed {chunks_processed} chunks in {batches_processed} batches")
    
    except Exception as e:
        logger.critical(f"Critical error in main processing loop: {str(e)}")
        # Try to save vector store if it was initialized
        try:
            if 'vector_store' in locals():
                vector_store.save()
                logger.info("Vector store saved during error recovery")
        except Exception as save_error:
            logger.error(f"Could not save vector store during error recovery: {str(save_error)}")

if __name__ == "__main__":
    main()