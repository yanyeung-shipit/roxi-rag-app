#!/usr/bin/env python3
"""
Script to process chunks until 75% completion.
This is a simplified and more reliable version.
"""

import os
import sys
import time
import pickle
import logging
import argparse
from typing import Set, Dict, Any, List, Optional, Tuple, Union
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("process_75_percent.log")
    ]
)
logger = logging.getLogger(__name__)

# Constants
DEFAULT_BATCH_SIZE = 5
DEFAULT_TARGET_PERCENTAGE = 75.0
DEFAULT_DELAY_SECONDS = 3
DOCUMENT_DATA_FILE = "document_data.pkl"

def get_processed_chunk_ids() -> Set[int]:
    """Get the IDs of chunks that have already been processed using VectorStore."""
    try:
        # Import our utility function from the Utils module
        # This avoids code duplication and ensures consistent results
        from utils.vector_store import VectorStore
        
        # Initialize VectorStore and use its get_processed_chunk_ids method
        vector_store = VectorStore()
        processed_ids = vector_store.get_processed_chunk_ids()
        return processed_ids
    except Exception as e:
        logger.error(f"Error getting processed chunk IDs: {e}")
        return set()

def get_progress() -> Dict[str, Any]:
    """Get current progress information."""
    try:
        from app import app, db
        from models import DocumentChunk
        from sqlalchemy import func
        
        # Vector store processed chunks
        processed_ids = get_processed_chunk_ids()
        processed_count = len(processed_ids)
        
        with app.app_context():
            # Database total chunks
            total_chunks = db.session.query(func.count(DocumentChunk.id)).scalar()
            
            # Calculate percentages
            if total_chunks > 0:
                percentage = (processed_count / total_chunks) * 100
                target_count = int(total_chunks * DEFAULT_TARGET_PERCENTAGE / 100)
                remaining = target_count - processed_count
                
                # Estimate time (2 seconds per chunk as a rough estimate)
                if remaining > 0:
                    est_seconds = remaining * 3  # Rough estimate
                    est_minutes = est_seconds // 60
                    est_hours = est_minutes // 60
                    est_minutes %= 60
                    
                    time_estimate = f"{est_hours}h {est_minutes}m"
                else:
                    time_estimate = "0m"
            else:
                percentage = 0
                target_count = 0
                remaining = 0
                time_estimate = "N/A"
            
            result = {
                "vector_store": processed_count,
                "database": total_chunks,
                "percentage": round(percentage, 1),
                "target_count": target_count,
                "remaining": max(0, target_count - processed_count),
                "time_estimate": time_estimate
            }
            
            # Log the progress
            logger.info(f"Vector store:   {processed_count} chunks")
            logger.info(f"Database:       {total_chunks} chunks in 23 documents")
            logger.info(f"----------------------------------------")
            logger.info(f"Progress:       {processed_count}/{total_chunks} chunks")
            logger.info(f"                {percentage:.1f}% complete")
            logger.info(f"Remaining:      {max(0, target_count - processed_count)} chunks")
            logger.info(f"Est. time:      {time_estimate} remaining")
            logger.info(f"========================================")
            
            return result
    except Exception as e:
        logger.error(f"Error getting progress: {e}")
        return {
            "error": str(e),
            "vector_store": 0,
            "database": 0,
            "percentage": 0
        }

def process_chunks(batch_size: int = DEFAULT_BATCH_SIZE, 
                  target_percentage: float = DEFAULT_TARGET_PERCENTAGE,
                  delay_seconds: int = DEFAULT_DELAY_SECONDS) -> None:
    """
    Process chunks until target percentage is reached.
    
    Args:
        batch_size: Number of chunks to process per batch
        target_percentage: Target percentage of completion
        delay_seconds: Delay between batches in seconds
    """
    try:
        logger.info(f"Starting chunk processing to {target_percentage}% completion")
        logger.info(f"Using batch size of {batch_size} with {delay_seconds}s delay")
        
        from app import app, db
        from models import Document, DocumentChunk
        from utils.vector_store import VectorStore
        
        # Initialize vector store
        vector_store = VectorStore()
        
        with app.app_context():
            # Main processing loop
            batch_count = 0
            while True:
                # Check current progress
                progress = get_progress()
                current_percentage = progress.get("percentage", 0)
                
                # Stop if target reached
                if current_percentage >= target_percentage:
                    logger.info(f"Target of {target_percentage}% reached! Processing complete.")
                    break
                
                # Get unprocessed chunks
                processed_ids = get_processed_chunk_ids()
                chunks = db.session.query(DocumentChunk).filter(
                    ~DocumentChunk.id.in_(processed_ids)
                ).order_by(DocumentChunk.id).limit(batch_size).all()
                
                if not chunks:
                    logger.info("No more unprocessed chunks found. Processing complete.")
                    break
                
                # Process this batch
                batch_count += 1
                logger.info(f"Processing batch #{batch_count} with {len(chunks)} chunks")
                
                successful_chunks = 0
                for chunk in chunks:
                    try:
                        # Skip if already processed (double-check)
                        if chunk.id in processed_ids:
                            continue
                        
                        # Get the document for citation information
                        document = db.session.query(Document).filter_by(id=chunk.document_id).first()
                        if not document:
                            logger.warning(f"Document {chunk.document_id} not found for chunk {chunk.id}")
                            continue
                        
                        # Prepare metadata
                        metadata = {
                            "document_id": chunk.document_id,
                            "chunk_id": chunk.id,
                            "page_number": chunk.page_number,
                            "chunk_index": chunk.chunk_index,
                            "source_type": "document",
                            "title": document.title,
                            "url": document.source_url,
                            "file_type": document.file_type,
                            "authors": document.authors,
                            "doi": document.doi,
                        }
                        
                        if document.publication_year:
                            metadata["publication_year"] = document.publication_year
                        
                        if document.formatted_citation:
                            metadata["formatted_citation"] = document.formatted_citation
                        
                        # Add to vector store
                        doc_id = vector_store.add_text(
                            text=chunk.text_content,
                            metadata=metadata
                        )
                        
                        if doc_id:
                            logger.info(f"Successfully processed chunk ID {chunk.id}")
                            successful_chunks += 1
                        else:
                            logger.error(f"Failed to add chunk ID {chunk.id} to vector store")
                    
                    except Exception as e:
                        logger.error(f"Error processing chunk ID {chunk.id}: {e}")
                        logger.error(traceback.format_exc())
                
                # Save after each batch
                try:
                    vector_store.save()
                    logger.info(f"Vector store saved successfully after batch #{batch_count}")
                except Exception as e:
                    logger.error(f"Error saving vector store: {e}")
                
                # Sleep before next batch
                if successful_chunks > 0:
                    logger.info(f"Processed {successful_chunks}/{len(chunks)} chunks in batch #{batch_count}")
                    logger.info(f"Waiting {delay_seconds} seconds before next batch...")
                    time.sleep(delay_seconds)
                else:
                    logger.warning(f"No chunks processed in batch #{batch_count}. Stopping.")
                    break
        
        # Final progress check
        final_progress = get_progress()
        final_percentage = final_progress.get("percentage", 0)
        logger.info(f"Processing complete. Final progress: {final_percentage:.1f}%")
        
        if final_percentage >= target_percentage:
            logger.info(f"Successfully reached target of {target_percentage}%")
        else:
            logger.warning(f"Processing stopped before reaching target. Reached {final_percentage:.1f}%")
    
    except Exception as e:
        logger.error(f"Error in process_chunks: {e}")
        logger.error(traceback.format_exc())

def main():
    """Main function to parse arguments and start processing."""
    parser = argparse.ArgumentParser(description="Process chunks to target percentage")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, 
                        help="Number of chunks to process per batch")
    parser.add_argument("--target", type=float, default=DEFAULT_TARGET_PERCENTAGE,
                        help="Target percentage of completion")
    parser.add_argument("--delay", type=int, default=DEFAULT_DELAY_SECONDS,
                        help="Delay between batches in seconds")
    parser.add_argument("--check", action="store_true", 
                        help="Just check progress without processing")
    
    args = parser.parse_args()
    
    # Log startup information
    logger.info(f"Running {os.path.basename(__file__)} with batch size {args.batch_size}")
    logger.info(f"Process started with PID: {os.getpid()}")
    
    # Run either check or processing
    if args.check:
        get_progress()
    else:
        process_chunks(
            batch_size=args.batch_size,
            target_percentage=args.target,
            delay_seconds=args.delay
        )

if __name__ == "__main__":
    main()