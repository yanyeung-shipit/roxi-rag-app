"""
Topic content processor functions for handling rheum.reviews topic pages.
These functions optimize memory usage and provide reliable content extraction.
"""
import logging
import re
import urllib.parse
from typing import Dict, List, Optional

import requests
import trafilatura
from bs4 import BeautifulSoup

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_minimal_content_for_topic(url: str) -> List[Dict]:
    """
    Create minimal content for a topic URL with optimized memory usage.
    This approach uses a lightweight extraction method and returns content in chunks.
    
    Args:
        url: The URL of the topic page
        
    Returns:
        List of dictionaries with 'text' and 'metadata' keys
    """
    logger.info(f"Creating minimal content for topic URL: {url}")
    
    try:
        # Extract topic name from URL
        parsed_url = urllib.parse.urlparse(url)
        path_parts = parsed_url.path.strip('/').split('/')
        topic_slug = path_parts[-1] if len(path_parts) > 1 else ""
        topic_name = topic_slug.replace('-', ' ').title()
        
        # Basic metadata
        base_metadata = {
            "source": url,
            "title": f"Topic: {topic_name}",
            "page_number": 1,
            "document_type": "website",
            "topic": topic_name
        }
        
        # Check if URL ends with trailing slash, add if missing
        if not url.endswith('/'):
            url = url + '/'
        
        # Download the content
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            logger.warning(f"Failed to download URL: {url}, status code: {response.status_code}")
            return []
            
        # Extract title from HTML
        html_content = response.text
        soup = BeautifulSoup(html_content, 'html.parser')
        page_title = soup.title.string if soup.title else ""
        
        if page_title:
            # Update metadata with actual page title
            base_metadata["title"] = page_title.strip()
        
        # Try different extraction methods and select the best result
        content = ""
        
        # Method 1: Trafilatura extraction (most reliable for article text)
        try:
            trafilatura_text = trafilatura.extract(html_content, include_comments=False, 
                                                include_tables=True, no_fallback=False)
            if trafilatura_text and len(trafilatura_text) > 500:
                content = trafilatura_text
                logger.info(f"Using trafilatura extraction for {url}")
        except Exception as e:
            logger.warning(f"Trafilatura extraction failed: {str(e)}")
        
        # Method 2: Simple BeautifulSoup extraction if trafilatura didn't work well
        if not content or len(content) < 500:
            try:
                # Extract main content from article or main tags
                main_content = soup.find('article') or soup.find('main') or soup.find('div', class_='content')
                if main_content:
                    content = main_content.get_text(separator="\n", strip=True)
                    logger.info(f"Using BeautifulSoup main content extraction for {url}")
            except Exception as e:
                logger.warning(f"BeautifulSoup main extraction failed: {str(e)}")
        
        # Method 3: Body text as fallback
        if not content or len(content) < 500:
            try:
                content = soup.body.get_text(separator="\n", strip=True)
                logger.info(f"Using body text extraction for {url}")
            except Exception as e:
                logger.warning(f"Body extraction failed: {str(e)}")
        
        # If we still don't have content, create a minimal placeholder
        if not content or len(content) < 100:
            logger.warning(f"No content extracted for {url}, creating minimal placeholder")
            content = f"Topic information for {topic_name}. This page contains medical information about {topic_name}."
        
        # Limit content size to avoid memory issues
        max_chars = 100000  # 100KB of text should be more than enough
        if len(content) > max_chars:
            logger.info(f"Limiting content size from {len(content)} to {max_chars} characters")
            content = content[:max_chars]
        
        # Clean the content
        content = re.sub(r'\n{3,}', '\n\n', content)  # Remove excessive newlines
        
        # Split into chunks of ~1000 characters with 200 char overlap
        chunks = []
        chunk_size = 1000
        overlap = 200
        
        content_length = len(content)
        
        # If content is short, just return a single chunk
        if content_length <= chunk_size:
            chunks.append({
                "text": content,
                "metadata": base_metadata
            })
            return chunks
        
        # Otherwise split into chunks
        start_pos = 0
        chunk_index = 0
        
        # Our goal is to split on paragraph breaks where possible
        while start_pos < content_length:
            # Calculate a potential end position
            pot_end_pos = min(start_pos + chunk_size, content_length)
            
            # Try to find a paragraph break near the potential end
            if pot_end_pos < content_length:
                # Look for newlines within the last 200 chars of potential chunk
                search_start = max(pot_end_pos - 200, start_pos)
                search_text = content[search_start:pot_end_pos]
                
                # Find the last paragraph break
                last_break = search_text.rfind('\n\n')
                
                if last_break != -1:
                    # Found a paragraph break, use it
                    end_pos = search_start + last_break
                else:
                    # No paragraph break, look for a single newline
                    last_newline = search_text.rfind('\n')
                    if last_newline != -1:
                        end_pos = search_start + last_newline
                    else:
                        # No newline, just use the potential end
                        end_pos = pot_end_pos
            else:
                # At the end of content
                end_pos = pot_end_pos
            
            # Get the chunk text
            chunk_text = content[start_pos:end_pos].strip()
            
            # Create chunk metadata
            chunk_metadata = base_metadata.copy()
            chunk_metadata["chunk_index"] = chunk_index
            
            # Add the chunk
            chunks.append({
                "text": chunk_text,
                "metadata": chunk_metadata
            })
            
            # Update for next iteration
            chunk_index += 1
            
            # Start the next chunk with some overlap, but ensure we move forward
            start_pos = max(start_pos + 1, end_pos - overlap)
        
        logger.info(f"Created {len(chunks)} chunks for topic URL: {url}")
        return chunks
        
    except Exception as e:
        logger.exception(f"Error creating content for topic URL {url}: {str(e)}")
        return []