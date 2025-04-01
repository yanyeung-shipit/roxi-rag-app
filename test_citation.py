import sys
import os
import logging
import json

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])

logger = logging.getLogger(__name__)

from utils.pdf_parser import process_pdf_generator
from utils.citation_manager import extract_citation_info

def test_document_citation(file_path, file_name):
    """
    Test the citation extraction from a PDF document
    """
    logger.info(f"Testing citation extraction for: {file_name}")
    
    # Step 1: Process the document to get chunks and metadata
    try:
        chunks, metadata = process_pdf(file_path, file_name)
        
        # Display document metadata
        logger.info(f"Document metadata extracted:")
        for key, value in metadata.items():
            if key in ['doi', 'authors', 'journal', 'publication_year', 'formatted_citation']:
                logger.info(f"  {key}: {value}")
        
        # Display citation information for the first chunk
        if chunks:
            first_chunk = chunks[0]
            logger.info(f"\nFirst chunk citation information:")
            meta = first_chunk['metadata']
            if 'formatted_citation' in meta:
                logger.info(f"  Citation: {meta['formatted_citation']}")
            else:
                logger.warning("  No formatted citation found in chunk metadata")
                
            # Step 3: Simulate what would be displayed to the user in a response
            logger.info("\nSource citation (as would appear in response):")
            citation = meta.get('formatted_citation', meta.get('citation', 'Unknown source'))
            logger.info(f"[1] {citation}")
            
            return True
        else:
            logger.warning("No chunks were extracted from the document")
            return False
            
    except Exception as e:
        logger.error(f"Error processing document: {e}")
        return False

if __name__ == "__main__":
    # Find a PDF file to test
    uploads_dir = "uploads"
    pdf_files = []
    
    for filename in os.listdir(uploads_dir):
        if filename.endswith(".pdf"):
            file_path = os.path.join(uploads_dir, filename)
            pdf_files.append((file_path, filename))
    
    if not pdf_files:
        logger.error("No PDF files found in uploads directory")
        sys.exit(1)
        
    # Test with the first PDF file
    file_path, file_name = pdf_files[0]
    test_document_citation(file_path, file_name)
