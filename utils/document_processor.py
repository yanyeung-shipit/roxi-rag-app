import os
import PyPDF2
from io import BytesIO
import logging
import re
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Dictionary of known citation mappings
CITATION_MAPPINGS = {
    "smolen2018": "Smolen, J. S., Aletaha, D., Barton, A., Burmester, G. R., Emery, P., Firestein, G. S., Kavanaugh, A., McInnes, I. B., Solomon, D. H., Strand, V., & Yamamoto, K. (2018). Rheumatoid arthritis. Nature reviews. Disease primers, 4, 18001. https://doi.org/10.1038/nrdp.2018.1",
    # Add more known citations as needed
}

def extract_citation_info(filename):
    """
    Extract citation information from the filename.
    
    Args:
        filename (str): Name of the file
        
    Returns:
        str: APA citation if available or a formatted citation based on filename
    """
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

def process_pdf(file_path, file_name):
    """
    Process a PDF file and extract text into chunks suitable for vector storage.
    
    Args:
        file_path (str): Path to the PDF file
        file_name (str): Name of the file for metadata
        
    Returns:
        list: List of dictionaries containing text chunks and metadata
    """
    logger.debug(f"Processing PDF: {file_path}")
    
    try:
        # Check file size - prevent processing extremely large files
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        logger.debug(f"PDF file size: {file_size_mb:.2f} MB")
        
        if file_size_mb > 20:  # Stricter limit - 20MB
            raise Exception(f"PDF file too large ({file_size_mb:.2f} MB). Maximum size is 20 MB.")
        
        # Extract text from PDF
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            num_pages = len(pdf_reader.pages)
            
            # Stricter limit on number of pages to prevent timeout
            max_pages = 20  # Reduced from 100 to 20
            if num_pages > max_pages:
                logger.warning(f"PDF has {num_pages} pages, limiting to first {max_pages} pages")
                num_pages = max_pages
            else:
                logger.debug(f"PDF has {num_pages} pages")
            
            # Extract text from each page with progress reporting
            all_text = []
            
            # Process only the first few pages to avoid timeout
            for page_num in range(min(num_pages, max_pages)):
                logger.debug(f"Processing page {page_num+1}/{min(num_pages, max_pages)}")
                
                try:
                    page = pdf_reader.pages[page_num]
                    text = page.extract_text()
                    
                    # Limit text length per page
                    if text:
                        if len(text) > 5000:  # Limit to 5000 chars per page
                            text = text[:5000] + "..."
                            logger.debug(f"Truncated text on page {page_num+1}")
                            
                        all_text.append({
                            "page": page_num + 1,
                            "text": text
                        })
                except Exception as page_error:
                    logger.warning(f"Error extracting text from page {page_num+1}: {str(page_error)}")
                    # Continue processing other pages
            
            logger.debug(f"Extracted text from {len(all_text)} pages")
            
            # Create chunks from the extracted text - simplified chunking
            chunks = []
            chunk_count = 0
            max_chunks = 100  # Limit total chunks to prevent timeouts
            
            for page_data in all_text:
                if chunk_count >= max_chunks:
                    logger.warning(f"Reached maximum chunk limit ({max_chunks}), stopping processing")
                    break
                    
                try:
                    # Use larger chunks with less overlap to reduce total number
                    page_chunks = chunk_text(page_data["text"], max_length=2000, overlap=100)
                    
                    for i, chunk in enumerate(page_chunks):
                        if chunk_count >= max_chunks:
                            break
                            
                        # Extract citation information from filename if possible
                        # Example: smolen2018 -> Smolen et al. (2018)
                        citation_info = extract_citation_info(file_name)
                        
                        chunks.append({
                            "text": chunk,
                            "metadata": {
                                "source_type": "pdf",
                                "title": file_name,
                                "page": page_data["page"],
                                "chunk_index": i,
                                "total_pages": num_pages,
                                "citation": citation_info
                            }
                        })
                        chunk_count += 1
                except Exception as chunk_error:
                    logger.warning(f"Error chunking text from page {page_data['page']}: {str(chunk_error)}")
                    # Continue processing other pages
            
            logger.debug(f"Created {len(chunks)} chunks from PDF")
            
            # If no chunks were created, return an error
            if not chunks:
                raise Exception("Could not extract any text from the PDF. The file may be scanned images or protected.")
                
            return chunks
            
    except Exception as e:
        logger.exception(f"Error processing PDF: {str(e)}")
        raise Exception(f"Failed to process PDF: {str(e)}")

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
