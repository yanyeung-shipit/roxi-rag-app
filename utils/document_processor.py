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
        # Extract text from PDF
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            num_pages = len(pdf_reader.pages)
            
            logger.debug(f"PDF has {num_pages} pages")
            
            # Extract text from each page
            all_text = []
            for page_num in range(num_pages):
                page = pdf_reader.pages[page_num]
                text = page.extract_text()
                if text:
                    all_text.append({
                        "page": page_num + 1,
                        "text": text
                    })
            
            # Create chunks from the extracted text
            chunks = []
            for page_data in all_text:
                page_chunks = chunk_text(page_data["text"], max_length=1000, overlap=200)
                
                for i, chunk in enumerate(page_chunks):
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
            
            logger.debug(f"Created {len(chunks)} chunks from PDF")
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
