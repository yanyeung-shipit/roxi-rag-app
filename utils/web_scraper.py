import trafilatura
import logging
import urllib.parse
from datetime import datetime
import re

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def scrape_website(url):
    """
    Scrape a website and extract text content into chunks suitable for vector storage.
    
    Args:
        url (str): URL of the website to scrape
        
    Returns:
        list: List of dictionaries containing text chunks and metadata
    """
    logger.debug(f"Scraping website: {url}")
    
    try:
        # Validate URL
        parsed_url = urllib.parse.urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise ValueError("Invalid URL format")
        
        # Fetch and extract content using Trafilatura
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            raise Exception(f"Failed to download content from {url}")
        
        # Extract main content
        text = trafilatura.extract(downloaded, include_links=True, include_images=False, 
                                  include_tables=True, deduplicate=True, no_fallback=False)
        
        if not text:
            logger.warning(f"No content extracted from {url}")
            raise Exception(f"No content extracted from {url}")
        
        # Extract title
        title = extract_title(downloaded, url)
        
        # Generate APA citation for the website
        citation = generate_website_citation(title, url)
        
        # Chunk the content
        text_chunks = chunk_text(text, max_length=1000, overlap=200)
        
        # Create chunks with metadata
        chunks = []
        for i, chunk in enumerate(text_chunks):
            chunks.append({
                "text": chunk,
                "metadata": {
                    "source_type": "website",
                    "title": title,
                    "url": url,
                    "chunk_index": i,
                    "citation": citation
                }
            })
        
        logger.debug(f"Created {len(chunks)} chunks from website")
        return chunks
        
    except Exception as e:
        logger.exception(f"Error scraping website: {str(e)}")
        raise Exception(f"Failed to scrape website: {str(e)}")

def extract_title(html, url):
    """
    Extract title from HTML content.
    
    Args:
        html (str): HTML content
        url (str): URL for fallback title
        
    Returns:
        str: Title of the webpage
    """
    try:
        # Try to extract using trafilatura
        title = trafilatura.extract_metadata(html, url=url).get('title', '')
        
        if not title:
            # Use domain name as fallback
            parsed_url = urllib.parse.urlparse(url)
            title = parsed_url.netloc
        
        return title
    except:
        # Use domain name as fallback
        parsed_url = urllib.parse.urlparse(url)
        return parsed_url.netloc
        
def generate_website_citation(title, url):
    """
    Generate an APA style citation for a website.
    
    Args:
        title (str): Website title
        url (str): Website URL
        
    Returns:
        str: APA formatted citation for the website
    """
    # Extract domain for organization name
    parsed_url = urllib.parse.urlparse(url)
    domain = parsed_url.netloc
    
    # Remove www. if present
    if domain.startswith('www.'):
        domain = domain[4:]
    
    # Split by dots and capitalize
    parts = domain.split('.')
    organization = ' '.join([part.capitalize() for part in parts[:-1]])
    
    # If no organization name could be extracted, use domain
    if not organization:
        organization = domain
        
    # Format date for citation
    current_date = datetime.now()
    retrieval_date = current_date.strftime("%B %d, %Y")
    
    # Generate the citation
    return f"{organization}. ({current_date.year}). {title}. Retrieved {retrieval_date}, from {url}"

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
            # Look for a paragraph break
            paragraph_break = text.rfind('\n\n', start, end)
            if paragraph_break != -1 and paragraph_break > start + (max_length / 2):
                end = paragraph_break + 2
            else:
                # Look for a sentence end
                sentence_end = max(
                    text.rfind('. ', start, end),
                    text.rfind('! ', start, end),
                    text.rfind('? ', start, end)
                )
                
                if sentence_end != -1 and sentence_end > start + (max_length / 2):
                    end = sentence_end + 2
                else:
                    # Look for a space
                    space = text.rfind(' ', start + (max_length / 2), end)
                    if space != -1:
                        end = space + 1
        
        # Add the chunk to our list
        chunks.append(text[start:end])
        
        # Move the start position for the next chunk, including overlap
        start = max(start + (max_length - overlap), end - overlap) if end < len(text) else len(text)
    
    return chunks
