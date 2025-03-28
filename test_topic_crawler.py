#!/usr/bin/env python3
"""
Test script to verify the improved crawler's ability to process topic pages.
This tool directly tests crawling a specific topic URL.
"""
import logging
import sys
import argparse
import requests
from bs4 import BeautifulSoup
import urllib.parse
from utils.web_scraper import scrape_website, _scrape_single_page, create_minimal_content_for_topic
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Test the crawler on a specific topic URL."""
    parser = argparse.ArgumentParser(description='Test crawler on specific topic URL')
    parser.add_argument('url', type=str, help='The URL to crawl')
    parser.add_argument('--max-pages', type=int, default=25, 
                      help='Maximum number of pages to crawl (default: 25)')
    parser.add_argument('--timeout', type=int, default=180, 
                      help='Maximum wait time in seconds (default: 180)')
    parser.add_argument('--direct', action='store_true', 
                      help='Also test direct HTTP request')
    args = parser.parse_args()
    
    url = args.url
    max_pages = args.max_pages
    timeout = args.timeout
    
    logger.info(f"Testing crawler on URL: {url}")
    logger.info(f"Max pages: {max_pages}, timeout: {timeout} seconds")
    
    # Try a direct HTTP request first to diagnose potential issues
    try:
        logger.info(f"Testing direct HTTP request to {url}")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"Direct request successful: {response.status_code}")
            content_length = len(response.text)
            logger.info(f"Content length: {content_length} characters")
            
            # See if there's a page title
            soup = BeautifulSoup(response.text, 'html.parser')
            title = soup.find('title')
            if title:
                logger.info(f"Page title: {title.text.strip()}")
            
            # Check for common content containers
            content_containers = [
                'article', '.article', '#article', '.content', '#content', 
                'main', '#main', '.main', '[role="main"]'
            ]
            
            found_containers = False
            for selector in content_containers:
                elements = []
                if selector.startswith('.'):
                    elements = soup.find_all(class_=selector[1:])
                elif selector.startswith('#'):
                    element = soup.find(id=selector[1:])
                    elements = [element] if element else []
                elif selector.startswith('['):
                    attr_name = selector.split('=')[0][1:]
                    attr_value = selector.split('=')[1].strip('"[]')
                    elements = soup.find_all(attrs={attr_name: attr_value})
                else:
                    elements = soup.find_all(selector)
                
                if elements:
                    found_containers = True
                    logger.info(f"Found {len(elements)} elements matching '{selector}'")
                    for i, element in enumerate(elements[:2]):
                        text = element.get_text(strip=True)
                        logger.info(f"  Content sample {i+1}: {text[:200]}...")
            
            if not found_containers:
                logger.warning("No standard content containers found on the page")
                
                # Look for any divs with substantial text
                substantial_divs = []
                for div in soup.find_all('div'):
                    text = div.get_text(strip=True)
                    if len(text) > 200:  # Arbitrary threshold for "substantial" text
                        substantial_divs.append((div, text))
                
                if substantial_divs:
                    logger.info(f"Found {len(substantial_divs)} divs with substantial text")
                    for i, (div, text) in enumerate(substantial_divs[:2]):
                        logger.info(f"  Div {i+1}: {text[:200]}...")
                else:
                    logger.warning("No divs with substantial text found")
        else:
            logger.error(f"Direct request failed: {response.status_code}")
    except Exception as e:
        logger.exception(f"Error during direct HTTP request: {str(e)}")
    
    # Now use the web scraper
    try:
        logger.info("\nTesting web scraper...")
        # Process the website
        results = scrape_website(url, max_pages=max_pages, max_wait_time=timeout)
        
        # Print statistics
        if results:
            logger.info(f"Successfully crawled {url}")
            logger.info(f"Extracted {len(results)} chunks")
            
            # Count unique pages
            unique_urls = set()
            for chunk in results:
                if 'url' in chunk['metadata']:
                    unique_urls.add(chunk['metadata']['url'])
            
            logger.info(f"Content from {len(unique_urls)} unique pages")
            
            # Print the first few unique URLs
            logger.info("Sample of crawled pages:")
            for url in list(unique_urls)[:10]:
                logger.info(f" - {url}")
                
            # Print sample chunks
            if results:
                logger.info("\nSample content:")
                # Show the first 2 chunks
                for i, sample in enumerate(results[:2]):
                    logger.info(f"\nChunk {i+1}:")
                    logger.info(f"Title: {sample['metadata'].get('title', 'Unknown')}")
                    logger.info(f"URL: {sample['metadata'].get('url', 'Unknown')}")
                    # Show more text for better evaluation
                    logger.info(f"Text excerpt: {sample['text'][:500]}...")
        else:
            logger.error(f"No content extracted from {url}")
            
            # Check if our fallback minimal content is working for topic pages
            parsed_url = urllib.parse.urlparse(url)
            topic_patterns = ['/topic/', '/disease/', '/diseases/', '/condition/', '/conditions/']
            is_topic_page = any(pattern in parsed_url.path for pattern in topic_patterns)
            
            if is_topic_page:
                logger.error("This is a topic page that should have at least minimal content created!")
                logger.error("Debugging the fallback minimal content creation...")
                
                # Create minimal content directly here as a test
                topic_name = parsed_url.path.strip('/').split('/')[-1].replace('-', ' ').title()
                minimal_text = f"Rheumatology Topic Page: {topic_name}\n\nThis is a specialized page about {topic_name} in rheumatology. The page URL is {url}."
                logger.info(f"Test minimal content that should have been created: {minimal_text}")
    except Exception as e:
        logger.exception(f"Error crawling {url}: {str(e)}")
        return 1
    
    return 0

def create_minimal_content(url):
    """
    Directly create minimal content with a manual approach, bypassing the crawler
    to test if our fallback works as expected.
    """
    logger.info(f"Creating minimal content directly for {url}")
    
    # Parse URL
    parsed_url = urllib.parse.urlparse(url)
    
    # Extract topic name from URL path
    topic_name = parsed_url.path.strip('/').split('/')[-1].replace('-', ' ').title()
    
    # Try to get page content directly
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        
        # Default title
        title = f"Rheumatology Topic: {topic_name}"
        content_text = ""
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract title
            title_element = soup.find('title')
            if title_element and title_element.text:
                title = title_element.text.strip()
                logger.info(f"Extracted title: {title}")
            
            # Extract content from article element
            article = soup.find('article')
            if article:
                content_text = article.get_text(separator=' ', strip=True)
                logger.info(f"Extracted {len(content_text)} chars from article element")
            
            # If no content from article, try other elements
            if not content_text or len(content_text) < 100:
                for selector in ['.content', '#content', 'main', '#main', '.main-content']:
                    element = None
                    if selector.startswith('.'):
                        elements = soup.find_all(class_=selector[1:])
                        if elements:
                            element = elements[0]
                    elif selector.startswith('#'):
                        element = soup.find(id=selector[1:])
                    else:
                        elements = soup.find_all(selector)
                        if elements:
                            element = elements[0]
                            
                    if element:
                        extracted = element.get_text(separator=' ', strip=True)
                        if len(extracted) > len(content_text):
                            content_text = extracted
                            logger.info(f"Extracted {len(content_text)} chars from {selector}")
        
        # Create content
        text = ""
        if content_text and len(content_text) > 200:
            # Format with title and content
            text = f"{title}\n\n{content_text}"
            logger.info(f"Created content with actual extracted text ({len(text)} chars)")
        else:
            # Create minimal fallback
            text = f"""Rheumatology Topic Page: {title}
URL: {url}

This is a specialized page about {topic_name} in rheumatology.
The page appears to contain information about this specific condition or topic."""
            logger.info(f"Created minimal fallback content ({len(text)} chars)")
        
        # Format as chunks
        citation = f"{title}. Retrieved {datetime.now().strftime('%B %d, %Y')}, from {url}"
        chunks = []
        
        # Split into chunks of ~800 chars
        chunk_size = 800
        overlap = 200
        
        # Simple chunking for testing
        if len(text) <= chunk_size:
            chunks.append({
                "text": text,
                "metadata": {
                    "source_type": "website",
                    "title": title,
                    "url": url,
                    "chunk_index": 0,
                    "page_number": 1,
                    "citation": citation,
                    "date_scraped": datetime.now().isoformat(),
                    "is_minimal_content": True
                }
            })
        else:
            # Split into overlapping chunks
            i = 0
            start = 0
            while start < len(text):
                end = min(start + chunk_size, len(text))
                # Don't create a tiny final chunk
                if len(text) - end < 200 and end < len(text):
                    end = len(text)
                
                chunk_text = text[start:end]
                chunks.append({
                    "text": chunk_text,
                    "metadata": {
                        "source_type": "website",
                        "title": title,
                        "url": url,
                        "chunk_index": i,
                        "page_number": 1,
                        "citation": citation,
                        "date_scraped": datetime.now().isoformat(),
                        "is_minimal_content": True
                    }
                })
                
                i += 1
                start = end - overlap if end < len(text) else len(text)
        
        logger.info(f"Created {len(chunks)} chunks for minimal content")
        return chunks
    
    except Exception as e:
        logger.exception(f"Error creating minimal content: {str(e)}")
        return []

if __name__ == "__main__":
    # Add optional command line flag to test minimal content directly
    parser = argparse.ArgumentParser(description='Test crawler on specific topic URL')
    parser.add_argument('url', type=str, help='The URL to crawl')
    parser.add_argument('--max-pages', type=int, default=25, 
                      help='Maximum number of pages to crawl (default: 25)')
    parser.add_argument('--timeout', type=int, default=180, 
                      help='Maximum wait time in seconds (default: 180)')
    parser.add_argument('--minimal', action='store_true', 
                      help='Test minimal content creation directly')
    args = parser.parse_args()
    
    if args.minimal:
        # Test minimal content directly
        url = args.url
        logger.info(f"Testing minimal content creation for {url}")
        
        # Use our imported function from web_scraper.py
        chunks = create_minimal_content_for_topic(url)
        
        if chunks:
            logger.info(f"Successfully created {len(chunks)} minimal content chunks")
            for i, chunk in enumerate(chunks[:5]):  # Show up to first 5 chunks
                logger.info(f"\nChunk {i+1}:")
                logger.info(f"Title: {chunk['metadata'].get('title', 'Unknown')}")
                logger.info(f"Text excerpt: {chunk['text'][:200]}...")
        else:
            logger.error("Failed to create minimal content with imported function")
            
            # Fall back to our local implementation for debugging
            logger.info("Trying with local implementation instead...")
            fallback_chunks = create_minimal_content(url)
            
            if fallback_chunks:
                logger.info(f"Local implementation created {len(fallback_chunks)} chunks")
                for i, chunk in enumerate(fallback_chunks[:2]):
                    logger.info(f"\nFallback chunk {i+1}:")
                    logger.info(f"Title: {chunk['metadata'].get('title', 'Unknown')}")
                    logger.info(f"Text excerpt: {chunk['text'][:200]}...")
            else:
                logger.error("Both implementations failed to create minimal content")
    else:
        # Run normal crawler test
        sys.exit(main())