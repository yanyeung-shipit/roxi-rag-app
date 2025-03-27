import os
import PyPDF2
from io import BytesIO
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

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
                            
                        chunks.append({
                            "text": chunk,
                            "metadata": {
                                "source_type": "pdf",
                                "title": file_name,
                                "page": page_data["page"],
                                "chunk_index": i,
                                "total_pages": num_pages
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
