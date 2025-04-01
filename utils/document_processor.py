import os
import gc
import logging
import re
import time
from datetime import datetime
import fitz  # PyMuPDF
from typing import Dict, List, Any, Optional, Tuple
import tempfile
from collections import defaultdict
import concurrent.futures

# We'll import the citation manager directly when needed to avoid circular imports

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Dictionary of known citation mappings (as fallback)
CITATION_MAPPINGS = {
    "smolen2018": "Smolen, J. S., Aletaha, D., Barton, A., Burmester, G. R., Emery, P., Firestein, G. S., Kavanaugh, A., McInnes, I. B., Solomon, D. H., Strand, V., & Yamamoto, K. (2018). Rheumatoid arthritis. Nature reviews. Disease primers, 4, 18001. https://doi.org/10.1038/nrdp.2018.1",
    # Add more known citations as needed
}

def extract_citation_info(filename, pdf_path=None):
    """
    Extract citation information from the filename or PDF content.
    Legacy function maintained for compatibility.
    
    Args:
        filename (str): Name of the file
        pdf_path (str, optional): Path to the PDF file
        
    Returns:
        str: APA citation if available or a formatted citation based on filename
    """
    # If we have a PDF path, use our advanced citation manager
    if pdf_path:
        # Import here to avoid circular imports
        from utils.citation_manager import extract_citation_info as citation_manager_extract
        citation, _ = citation_manager_extract(filename, pdf_path)
        return citation
        
    # Legacy code for backward compatibility
    # Remove file extension if present
    base_name = os.path.splitext(filename)[0].lower()
    
    # Check if we have a pre-defined citation for this file
    if base_name in CITATION_MAPPINGS:
        return CITATION_MAPPINGS[base_name]
    
    # Current year for retrieval date
    current_year = datetime.now().year
    formatted_date = datetime.now().strftime("%B %d, %Y")
    
    # Try to extract author and year from filename pattern (e.g., "smith2020")
    match = re.match(r'([a-z]+)(\d{4})', base_name)
    if match:
        author = match.group(1).capitalize()
        year = match.group(2)
        
        # Generate a title from the filename, replacing underscores with spaces
        title_parts = base_name.split('_')
        if len(title_parts) > 1:
            # If there are underscores in the name, use them to create a better title
            title = ' '.join([p.capitalize() for p in title_parts if p != author.lower() and p != year])
        else:
            # Otherwise just use a generic title
            title = "Research Paper"
        
        # Format in APA 7th edition style
        return f"{author}, {author[0].upper()}. ({year}). {title}. Retrieved {formatted_date}."
    
    # Try to handle filenames with underscores as title elements (e.g., "cancer_research_2020.pdf")
    match = re.match(r'(.+)_(\d{4})', base_name)
    if match:
        title = match.group(1).replace('_', ' ').title()
        year = match.group(2)
        
        # Format as APA citation with title and year
        return f"{title} ({year}). Retrieved {formatted_date}."
    
    # Try to handle filenames with hyphens (e.g., "medical-journal-2019.pdf")
    match = re.match(r'(.+)-(\d{4})', base_name)
    if match:
        title = match.group(1).replace('-', ' ').title()
        year = match.group(2)
        
        # Format as APA citation with title and year
        return f"{title} ({year}). Retrieved {formatted_date}."
        
    # Clean the filename to create a better title
    title = base_name.replace('_', ' ').replace('-', ' ').title()
    
    # Default APA format for document with unknown year and author
    return f"{title} (n.d.). Retrieved {formatted_date}."

def extract_pdf_metadata(pdf_doc, file_name) -> Dict[str, Any]:
    """
    Extract metadata from a PDF document, including DOI and citation information.
    
    Args:
        pdf_doc (fitz.Document): Open PyMuPDF document
        file_name (str): Name of the file
        
    Returns:
        Dict[str, Any]: Metadata dictionary
    """
    metadata = {}
    
    # Basic PDF metadata
    try:
        pdf_metadata = pdf_doc.metadata
        if pdf_metadata:
            metadata['title'] = pdf_metadata.get('title', file_name)
            metadata['author'] = pdf_metadata.get('author', '')
            metadata['subject'] = pdf_metadata.get('subject', '')
            metadata['keywords'] = pdf_metadata.get('keywords', '')
            metadata['creator'] = pdf_metadata.get('creator', '')
    except Exception as e:
        logger.warning(f"Error extracting PDF metadata: {str(e)}")
    
    # Set defaults if not found
    if 'title' not in metadata or not metadata['title']:
        metadata['title'] = file_name
    
    return metadata

def process_pdf_lazy(file_path, filename):
    """
    Generator that yields chunks one at a time.
    """
    import fitz  # PyMuPDF or whatever library you're using
    doc = fitz.open(file_path)
    
    metadata = {
        'page_count': len(doc),
        # You can extract more metadata here if needed
    }

    for i, page in enumerate(doc):
        try:
            text = page.get_text()
            if not text.strip():
                continue

            # You can add your own chunking logic here
            yield {
                'text': text,
                'metadata': {
                    'page': i + 1,
                    'filename': filename
                }
            }
        except Exception as e:
            # Optional: yield a warning or log and skip
            continue

    doc.close()
    yield {'__metadata__': metadata}  # final yield is metadata

def bulk_process_pdfs(pdf_files, batch_size=3):
    """
    Process multiple PDF files in a memory-efficient way.
    
    Args:
        pdf_files (List[Tuple[str, str]]): List of (file_path, file_name) tuples
        batch_size (int): Number of PDFs to process in each batch (default: 3)
        
    Returns:
        List[Tuple[List, Dict]]: List of (chunks, metadata) tuples
    """
    results = []
    
    # Process in smaller batches to avoid memory issues
    for i in range(0, len(pdf_files), batch_size):
        batch = pdf_files[i:i+batch_size]
        batch_results = []
        
        for file_path, file_name in batch:
            try:
                logger.debug(f"Processing PDF in batch: {file_name}")
                # Add sleep to allow some background processes to complete
                time.sleep(0.5)
                
                chunks, metadata = process_pdf(file_path, file_name)
                batch_results.append((chunks, metadata))
                
                # Force garbage collection after each file
                gc.collect()
            except Exception as e:
                logger.error(f"Error processing PDF {file_name}: {str(e)}")
                batch_results.append(([], {'error': str(e)}))
        
        # Extend results with this batch
        results.extend(batch_results)
        
        # Force more aggressive garbage collection after each batch
        for _ in range(3):
            gc.collect()
        
        # Add a small delay between batches to allow system to stabilize
        time.sleep(1)
    
    return results

def chunk_text(text, max_length=1000, overlap=200):
    """
    Split text into overlapping chunks of specified maximum length.
    
    Args:
        text (str): Text to split into chunks
        max_length (int): Maximum length of each chunk
        overlap (int): Number of characters to overlap between chunks
        
    Returns:
        list: List of text chunks
    """
    # Clean the text
    text = text.replace('\n\n', ' ').replace('\n', ' ').strip()
    
    # If text is shorter than max_length, return it as a single chunk
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        # Get a chunk of max_length or the remaining text if shorter
        end = min(start + max_length, len(text))
        
        # If this is not the end of the text, try to find a good breaking point
        if end < len(text):
            # Look for a period followed by space to break at for better semantics
            period_pos = text.rfind('. ', start + max_length - 100, end)
            if period_pos != -1:
                end = period_pos + 1  # Include the period
            else:
                # Look for a space to break at
                while end > start + max_length - 100 and text[end] != ' ':
                    end -= 1
                    
                # If we couldn't find a space, just use the maximum length
                if end <= start + max_length - 100:
                    end = start + max_length
        
        # Add the chunk to our list
        chunks.append(text[start:end])
        
        # Move the start position for the next chunk, including overlap
        start = end - overlap if end < len(text) else len(text)
    
    return chunks
