import sys
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])

logger = logging.getLogger(__name__)

from utils.citation_manager import extract_citation_info, extract_doi_from_pdf

def test_single_pdf():
    """Test citation extraction on a single PDF file"""
    uploads_dir = "uploads"
    pdf_files = []
    
    # Find all PDF files
    for filename in os.listdir(uploads_dir):
        if filename.endswith(".pdf"):
            file_path = os.path.join(uploads_dir, filename)
            pdf_files.append((file_path, filename))
    
    if not pdf_files:
        logger.error("No PDF files found in uploads directory")
        return
    
    # Choose the first PDF file
    file_path, file_name = pdf_files[0]
    logger.info(f"Testing citation extraction for: {file_name}")
    
    # Extract DOI directly
    doi = extract_doi_from_pdf(file_path)
    logger.info(f"DOI extracted from PDF: {doi}")
    
    # Get citation information
    citation, metadata = extract_citation_info(file_name, file_path)
    logger.info(f"Citation: {citation}")
    
    if metadata:
        logger.info("Metadata extracted:")
        if 'DOI' in metadata:
            logger.info(f"  DOI: {metadata['DOI']}")
        if 'title' in metadata:
            logger.info(f"  Title: {metadata['title']}")
        if 'author' in metadata:
            authors = []
            for author in metadata['author'][:3]:  # Show first 3 authors
                if 'family' in author and 'given' in author:
                    authors.append(f"{author['family']}, {author['given']}")
                elif 'family' in author:
                    authors.append(author['family'])
            logger.info(f"  Authors: {', '.join(authors)}")
        if 'container-title' in metadata:
            journal = metadata['container-title']
            if isinstance(journal, list) and journal:
                journal = journal[0]
            logger.info(f"  Journal: {journal}")
        if 'published' in metadata and 'date-parts' in metadata['published']:
            date_parts = metadata['published']['date-parts']
            if date_parts and date_parts[0]:
                logger.info(f"  Year: {date_parts[0][0]}")
    else:
        logger.warning("No metadata extracted from citation sources")

if __name__ == "__main__":
    test_single_pdf()