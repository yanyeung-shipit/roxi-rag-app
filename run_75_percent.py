#!/usr/bin/env python3
"""
Simple script to process chunks until we reach 75% completion.
This script is meant to be run directly and will continue until completion.
"""

import sys
import logging
import pickle
import os
import time
from typing import Set, Dict, Any, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("process_75_percent.log")
    ]
)
logger = logging.getLogger()

# Constants
TARGET_PERCENTAGE = 75.0
BATCH_SIZE = 10
DELAY_SECONDS = 5
DOCUMENT_DATA_FILE = "document_data.pkl"

def get_processed_chunk_ids() -> Set[int]:
    """Get IDs of chunks that have already been processed."""
    processed_ids = set()
    try:
        # Load document data from the pickle file
        if os.path.exists(DOCUMENT_DATA_FILE):
            with open(DOCUMENT_DATA_FILE, 'rb') as f:
                loaded_data = pickle.load(f)
                documents = loaded_data.get('documents', {})
                
                # Extract chunk_id from metadata if it exists
                for doc_id, doc_data in documents.items():
                    metadata = doc_data.get('metadata', {})
                    if 'chunk_id' in metadata and metadata['chunk_id'] is not None:
                        try:
                            chunk_id = int(metadata['chunk_id'])
                            processed_ids.add(chunk_id)
                        except (ValueError, TypeError):
                            pass
            
            logger.info(f"Found {len(processed_ids)} processed chunk IDs in vector store")
        else:
            logger.warning(f"Vector store data file {DOCUMENT_DATA_FILE} not found")
        
        return processed_ids
    except Exception as e:
        logger.error(f"Error getting processed chunk IDs: {e}")
        return set()

def process_chunks_to_75_percent():
    """Process chunks until we reach 75% completion."""
    try:
        from app import app, db
        from models import Document, DocumentChunk
        from utils.vector_store import VectorStore
        from sqlalchemy import func
        
        logger.info(f"Starting chunk processing to reach {TARGET_PERCENTAGE}% completion")
        logger.info(f"Using batch size of {BATCH_SIZE} with {DELAY_SECONDS}s delay between batches")
        
        with app.app_context():
            # Get total chunks count
            total_chunks = db.session.query(func.count(DocumentChunk.id)).scalar()
            target_chunks = int(total_chunks * TARGET_PERCENTAGE / 100)
            
            # Get processed chunks
            processed_ids = get_processed_chunk_ids()
            processed_count = len(processed_ids)
            
            logger.info(f"Current progress: {processed_count}/{total_chunks} chunks ({processed_count/total_chunks*100:.1f}%)")
            logger.info(f"Target: {target_chunks} chunks ({TARGET_PERCENTAGE}%)")
            
            if processed_count >= target_chunks:
                logger.info(f"Target already reached! No processing needed.")
                return
            
            chunks_needed = target_chunks - processed_count
            logger.info(f"Need to process {chunks_needed} more chunks")
            
            # Start processing
            batch_count = 0
            max_retries = 3
            vector_store = VectorStore()
            
            while processed_count < target_chunks:
                batch_count += 1
                
                # Get unprocessed chunks
                chunks = db.session.query(DocumentChunk).filter(
                    ~DocumentChunk.id.in_(processed_ids)
                ).order_by(DocumentChunk.id).limit(BATCH_SIZE).all()
                
                if not chunks:
                    logger.info("No more chunks to process")
                    break
                
                logger.info(f"Processing batch {batch_count} ({len(chunks)} chunks)")
                
                # Process each chunk
                for chunk in chunks:
                    # Skip if already processed
                    if chunk.id in processed_ids:
                        continue
                    
                    # Prepare metadata
                    metadata = {
                        "document_id": chunk.document_id,
                        "chunk_id": chunk.id,
                        "page_number": chunk.page_number,
                        "chunk_index": chunk.chunk_index,
                        "source_type": "document",
                    }
                    
                    # Get document info
                    document = db.session.query(Document).filter_by(id=chunk.document_id).first()
                    if document:
                        metadata.update({
                            "title": document.title,
                            "url": document.source_url,
                            "file_type": document.file_type,
                            "authors": document.authors,
                            "doi": document.doi,
                        })
                        
                        if document.publication_year:
                            metadata["publication_year"] = document.publication_year
                            
                        if document.formatted_citation:
                            metadata["formatted_citation"] = document.formatted_citation
                    
                    # Try to add to vector store with retries
                    success = False
                    retry_count = 0
                    
                    while not success and retry_count < max_retries:
                        try:
                            doc_id = vector_store.add_text(
                                text=chunk.text_content,
                                metadata=metadata
                            )
                            success = doc_id is not None
                            if success:
                                logger.info(f"Successfully processed chunk ID: {chunk.id}")
                                processed_ids.add(chunk.id)
                                processed_count += 1
                            else:
                                logger.warning(f"Failed to process chunk ID: {chunk.id}")
                                retry_count += 1
                        except Exception as e:
                            logger.error(f"Error processing chunk ID {chunk.id}: {e}")
                            retry_count += 1
                            time.sleep(1)  # Short delay before retry
                
                # Check progress
                percentage = (processed_count / total_chunks) * 100
                logger.info(f"Progress: {processed_count}/{total_chunks} chunks ({percentage:.1f}%)")
                
                # Save vector store after each batch
                try:
                    vector_store.save()
                    logger.info("Vector store saved successfully")
                except Exception as e:
                    logger.error(f"Error saving vector store: {e}")
                
                # Delay before next batch
                if processed_count < target_chunks:
                    logger.info(f"Waiting {DELAY_SECONDS} seconds before next batch...")
                    time.sleep(DELAY_SECONDS)
            
            final_percentage = (processed_count / total_chunks) * 100
            logger.info(f"Processing complete. Final progress: {processed_count}/{total_chunks} chunks ({final_percentage:.1f}%)")
            
            if final_percentage >= TARGET_PERCENTAGE:
                logger.info(f"Target of {TARGET_PERCENTAGE}% reached successfully!")
            else:
                logger.warning(f"Processing ended before reaching target. Reached {final_percentage:.1f}%")
    
    except Exception as e:
        logger.error(f"Error in process_chunks_to_75_percent: {e}")

if __name__ == "__main__":
    process_chunks_to_75_percent()