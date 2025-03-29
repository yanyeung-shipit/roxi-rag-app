import sys
import os
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])

logger = logging.getLogger(__name__)

from utils.document_processor import process_pdf
from utils.citation_manager import extract_citation_info

def test_process_flow():
    """Test the full citation extraction and processing flow"""
    # Find a PDF file to test with
    uploads_dir = "uploads"
    pdf_files = []
    
    for filename in os.listdir(uploads_dir):
        if filename.endswith(".pdf"):
            file_path = os.path.join(uploads_dir, filename)
            pdf_files.append((file_path, filename))
    
    if not pdf_files:
        logger.error("No PDF files found in uploads directory")
        return
    
    # Choose a different PDF file (the second one if available)
    file_path, file_name = pdf_files[1] if len(pdf_files) > 1 else pdf_files[0]
    logger.info(f"Testing with file: {file_name}")
    
    # Step 1: Process the PDF with our document_processor
    try:
        chunks, metadata = process_pdf(file_path, file_name)
        
        # Log document metadata
        logger.info("Document metadata:")
        for key, value in metadata.items():
            logger.info(f"  {key}: {value}")
        
        # Check the first chunk's metadata for citation information
        if chunks:
            logger.info("\nFirst chunk metadata:")
            chunk_meta = chunks[0]['metadata']
            for key, value in chunk_meta.items():
                logger.info(f"  {key}: {value}")
            
            # Verify citation fields
            if 'citation' in chunk_meta:
                logger.info("\nCitation found in chunk metadata ✓")
            else:
                logger.warning("\nNo citation field in chunk metadata ✗")
                
            if 'formatted_citation' in chunk_meta:
                logger.info("Formatted citation found in chunk metadata ✓")
            else:
                logger.warning("No formatted_citation field in chunk metadata ✗")
        else:
            logger.warning("No chunks generated from the PDF")
    
    except Exception as e:
        logger.error(f"Error processing PDF: {e}")

if __name__ == "__main__":
    test_process_flow()