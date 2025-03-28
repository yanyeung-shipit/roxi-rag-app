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
    logger.info(f"Scraping website: {url}")
    
    try:
        # Validate URL
        parsed_url = urllib.parse.urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise ValueError("Invalid URL format")
        
        # Fetch and extract content using Trafilatura
        logger.debug(f"Fetching content from URL: {url}")
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            logger.error(f"Failed to download content from {url}")
            raise Exception(f"Failed to download content from {url}")
        
        logger.debug(f"Downloaded content length: {len(downloaded)} bytes")
        
        # Extract main content with improved options
        logger.debug("Extracting text content with trafilatura")
        text = trafilatura.extract(
            downloaded, 
            include_links=True, 
            include_images=False, 
            include_tables=True, 
            deduplicate=True, 
            no_fallback=False,
            favor_precision=False  # Set to False to extract more content
        )
        
        # Check if content was extracted
        if not text or len(text.strip()) < 50:  # Minimum meaningful content
            logger.warning(f"No significant content extracted from {url}")
            
            # Try with different extraction parameters as fallback
            logger.debug("Trying alternate extraction method")
            text = trafilatura.extract(
                downloaded,
                include_comments=True,  # Include comments which may contain useful text
                include_tables=True,
                no_fallback=False,
                target_language="en"
            )
            
            if not text or len(text.strip()) < 50:
                logger.error(f"Failed to extract any meaningful content from {url}")
                raise Exception(f"No meaningful content extracted from {url}")
        
        logger.info(f"Successfully extracted {len(text)} characters from {url}")
        
        # Extract title with enhanced method
        title = extract_title(downloaded, url)
        logger.info(f"Extracted title: {title}")
        
        # Generate APA citation for the website
        citation = generate_website_citation(title, url)
        logger.debug(f"Generated citation: {citation}")
        
        # Chunk the content with smaller chunks for more precise retrieval
        text_chunks = chunk_text(text, max_length=800, overlap=200)
        logger.info(f"Created {len(text_chunks)} chunks from website content")
        
        # Create chunks with comprehensive metadata
        chunks = []
        for i, chunk in enumerate(text_chunks):
            chunks.append({
                "text": chunk,
                "metadata": {
                    "source_type": "website",
                    "title": title,
                    "url": url,
                    "chunk_index": i,
                    "citation": citation,
                    "date_scraped": datetime.now().isoformat()
                }
            })
        
        # Log sample chunk for verification
        if chunks:
            logger.debug(f"Sample chunk: {chunks[0]['text'][:100]}...")
            logger.debug(f"Sample metadata: {chunks[0]['metadata']}")
        
        logger.info(f"Created {len(chunks)} chunks from website {url}")
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
        metadata = trafilatura.extract_metadata(html, url=url)
        logger.debug(f"Extracted metadata: {metadata}")
        
        title = metadata.get('title', '')
        
        if not title:
            # Try to extract from HTML directly using regex
            logger.debug("Title not found in metadata, trying regex extraction")
            import re
            title_match = re.search('<title>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
            if title_match:
                title = title_match.group(1).strip()
                logger.debug(f"Found title with regex: {title}")
            
        if not title:
            # Use domain name as fallback
            parsed_url = urllib.parse.urlparse(url)
            title = parsed_url.netloc
            logger.debug(f"Using domain as fallback title: {title}")
        
        return title
    except Exception as e:
        logger.exception(f"Error extracting title: {str(e)}")
        # Use domain name as fallback
        parsed_url = urllib.parse.urlparse(url)
        domain = parsed_url.netloc
        logger.debug(f"Using domain as exception fallback title: {domain}")
        return domain
        
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
