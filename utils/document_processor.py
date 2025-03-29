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

def process_pdf(file_path, file_name, extract_citation=True):
    """
    Process a PDF file and extract text into chunks suitable for vector storage.
    Enhanced version that uses PyMuPDF and supports DOI extraction and citation lookup.
    
    Args:
        file_path (str): Path to the PDF file
        file_name (str): Name of the file for metadata
        extract_citation (bool): Whether to extract citation info (can be time-consuming)
        
    Returns:
        Tuple[list, Dict]: Tuple of (chunks, document_metadata)
    """
    logger.debug(f"Processing PDF: {file_path}")
    
    try:
        # Check file size - prevent processing extremely large files
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        logger.debug(f"PDF file size: {file_size_mb:.2f} MB")
        
        if file_size_mb > 20:  # Limit - 20MB
            raise Exception(f"PDF file too large ({file_size_mb:.2f} MB). Maximum size is 20 MB.")
        
        # Document metadata to return
        document_metadata = {
            'file_size': int(file_size_mb * 1024 * 1024),
            'doi': None,
            'authors': None,
            'journal': None,
            'publication_year': None,
            'volume': None,
            'issue': None,
            'pages': None,
            'formatted_citation': None
        }
        
        # Extract text from PDF using PyMuPDF (faster and better quality than PyPDF2)
        pdf_doc = fitz.open(file_path)
        num_pages = len(pdf_doc)
        document_metadata['page_count'] = num_pages
        
        # Extract document metadata (like title, author, etc.)
        pdf_metadata = extract_pdf_metadata(pdf_doc, file_name)
        if 'title' in pdf_metadata:
            document_metadata['title'] = pdf_metadata['title']
        
        # Stricter limit on number of pages to prevent timeout
        max_pages = min(50, num_pages)  # Process up to 50 pages
        if num_pages > max_pages:
            logger.warning(f"PDF has {num_pages} pages, limiting to first {max_pages} pages")
        else:
            logger.debug(f"PDF has {num_pages} pages")
        
        # Extract text from each page with progress reporting
        all_text = []
        
        # Process pages in batches to avoid memory issues
        batch_size = 5
        for batch_start in range(0, min(max_pages, num_pages), batch_size):
            batch_end = min(batch_start + batch_size, min(max_pages, num_pages))
            
            # Process this batch of pages
            for page_num in range(batch_start, batch_end):
                logger.debug(f"Processing page {page_num+1}/{min(max_pages, num_pages)}")
                
                try:
                    page = pdf_doc[page_num]
                    
                    # For scientific papers, we want blocks of text to preserve layout
                    # This is better for multi-column documents
                    text = page.get_text("text")
                    
                    # Limit text length per page for memory safety
                    if text:
                        if len(text) > 10000:  # Limit to 10000 chars per page
                            text = text[:10000] + "..."
                            logger.debug(f"Truncated text on page {page_num+1}")
                            
                        all_text.append({
                            "page": page_num + 1,
                            "text": text
                        })
                except Exception as page_error:
                    logger.warning(f"Error extracting text from page {page_num+1}: {str(page_error)}")
                    # Continue processing other pages
            
            # Force garbage collection to free memory after each batch
            gc.collect()
        
        logger.debug(f"Extracted text from {len(all_text)} pages")
        
        # Extract citation information if requested
        if extract_citation:
            # Import here to avoid circular imports
            from utils.citation_manager import extract_citation_info
            
            # Use our enhanced citation manager to get citation and metadata
            formatted_citation, citation_metadata = extract_citation_info(file_name, file_path)
            document_metadata['formatted_citation'] = formatted_citation
            
            # Copy citation metadata to document metadata if available
            if citation_metadata:
                if 'DOI' in citation_metadata:
                    document_metadata['doi'] = citation_metadata['DOI']
                
                # Extract authors
                if 'author' in citation_metadata:
                    authors_list = []
                    for author in citation_metadata['author']:
                        if 'family' in author:
                            if 'given' in author:
                                authors_list.append(f"{author['family']}, {author['given']}")
                            else:
                                authors_list.append(author['family'])
                    document_metadata['authors'] = "; ".join(authors_list)
                
                # Extract other metadata
                if 'container-title' in citation_metadata:
                    if isinstance(citation_metadata['container-title'], list):
                        document_metadata['journal'] = citation_metadata['container-title'][0]
                    else:
                        document_metadata['journal'] = citation_metadata['container-title']
                
                if 'published' in citation_metadata and 'date-parts' in citation_metadata['published']:
                    date_parts = citation_metadata['published']['date-parts']
                    if date_parts and date_parts[0]:
                        document_metadata['publication_year'] = date_parts[0][0]
                
                document_metadata['volume'] = citation_metadata.get('volume', None)
                document_metadata['issue'] = citation_metadata.get('issue', None)
                document_metadata['pages'] = citation_metadata.get('page', None)
        
        # Create chunks from the extracted text
        chunks = []
        chunk_count = 0
        max_chunks = 200  # Allow more chunks for scientific papers
        
        for page_data in all_text:
            if chunk_count >= max_chunks:
                logger.warning(f"Reached maximum chunk limit ({max_chunks}), stopping processing")
                break
                
            try:
                # Use larger chunks with less overlap for scientific papers
                page_chunks = chunk_text(page_data["text"], max_length=1500, overlap=150)
                
                for i, chunk in enumerate(page_chunks):
                    if chunk_count >= max_chunks:
                        break
                        
                    # Get citation from document metadata if available
                    citation_info = document_metadata.get('formatted_citation', None)
                    if not citation_info:
                        # Call our own extract_citation_info function
                        citation_info = extract_citation_info(file_name)
                    
                    chunks.append({
                        "text": chunk,
                        "metadata": {
                            "source_type": "pdf",
                            "title": document_metadata.get('title', file_name),
                            "page": page_data["page"],
                            "chunk_index": i,
                            "total_pages": num_pages,
                            "citation": citation_info,
                            "doi": document_metadata.get('doi', None)
                        }
                    })
                    chunk_count += 1
            except Exception as chunk_error:
                logger.warning(f"Error chunking text from page {page_data['page']}: {str(chunk_error)}")
                # Continue processing other pages
        
        # Close the PDF to free resources
        pdf_doc.close()
        
        logger.debug(f"Created {len(chunks)} chunks from PDF")
        
        # If no chunks were created, return an error
        if not chunks:
            raise Exception("Could not extract any text from the PDF. The file may be scanned images or protected.")
                
        return chunks, document_metadata
            
    except Exception as e:
        logger.exception(f"Error processing PDF: {str(e)}")
        raise Exception(f"Failed to process PDF: {str(e)}")

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
