import trafilatura
import logging
import urllib.parse
from datetime import datetime
import re
import requests
from bs4 import BeautifulSoup
import time
import threading
import queue

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def _extract_links(html, base_url):
    """
    Extract links from HTML content that belong to the same domain.
    
    Args:
        html (str): HTML content
        base_url (str): Base URL to match domain
        
    Returns:
        list: List of URLs belonging to the same domain
    """
    try:
        soup = BeautifulSoup(html, 'html.parser')
        base_domain = urllib.parse.urlparse(base_url).netloc
        
        links = []
        
        # Top priority links - look for navigation menus and content areas where valuable links are likely to be
        # Common navigation class/id patterns
        nav_selectors = [
            'nav', '.nav', '.menu', '.navigation', '#nav', '#menu', '#navigation',
            '.navbar', '.header-menu', '.main-menu', '.primary-menu', '.site-menu',
            'header', '.header', '#header', '.sidebar', '#sidebar', 
            '.main-nav', '.top-nav', '.categories', '.chapters', '.sections',
            '[role="navigation"]', '.topics', '#topics', '.diseases', '#diseases',
            '.conditions', '#conditions'
        ]
        
        # Find all navigation elements
        nav_elements = []
        for selector in nav_selectors:
            if selector.startswith('.'):
                nav_elements.extend(soup.find_all(class_=selector[1:]))
            elif selector.startswith('#'):
                found_element = soup.find(id=selector[1:])
                if found_element:
                    nav_elements.append(found_element)
            elif selector.startswith('['):
                # Handle attribute selectors like [role="navigation"]
                attr_name = selector.split('=')[0][1:]
                attr_value = selector.split('=')[1].strip('"[]')
                nav_elements.extend(soup.find_all(attrs={attr_name: attr_value}))
            else:
                nav_elements.extend(soup.find_all(selector))
        
        # Process links from navigation areas first (these are likely more important)
        priority_links = []
        for nav in nav_elements:
            for a_tag in nav.find_all('a', href=True):
                href = a_tag['href']
                
                # Handle relative URLs
                if href.startswith('/'):
                    parsed_base = urllib.parse.urlparse(base_url)
                    href = f"{parsed_base.scheme}://{parsed_base.netloc}{href}"
                elif not href.startswith(('http://', 'https://')):
                    # Skip anchors and javascript links
                    if href.startswith('#') or href.startswith('javascript:'):
                        continue
                    # Other relative paths
                    if base_url.endswith('/'):
                        href = f"{base_url}{href}"
                    else:
                        href = f"{base_url}/{href}"
                
                # Only include links from the same domain
                parsed_href = urllib.parse.urlparse(href)
                if parsed_href.netloc == base_domain:
                    # Remove fragments and normalize URL
                    href = urllib.parse.urljoin(href, urllib.parse.urlparse(href).path)
                    priority_links.append(href)
                    
        # Process remaining links from the page
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            
            # Handle relative URLs
            if href.startswith('/'):
                parsed_base = urllib.parse.urlparse(base_url)
                href = f"{parsed_base.scheme}://{parsed_base.netloc}{href}"
            elif not href.startswith(('http://', 'https://')):
                # Skip anchors and javascript links
                if href.startswith('#') or href.startswith('javascript:'):
                    continue
                # Other relative paths
                if base_url.endswith('/'):
                    href = f"{base_url}{href}"
                else:
                    href = f"{base_url}/{href}"
            
            # Only include links from the same domain
            parsed_href = urllib.parse.urlparse(href)
            if parsed_href.netloc == base_domain:
                # Remove fragments and normalize URL
                href = urllib.parse.urljoin(href, urllib.parse.urlparse(href).path)
                links.append(href)
        
        # Give priority to navigation links by placing them first
        combined_links = priority_links + [link for link in links if link not in set(priority_links)]
        
        # Remove duplicates
        unique_links = list(dict.fromkeys(combined_links))  # Preserves order while removing duplicates
        
        # Look for disease/condition specific links which are high value
        rheumatology_keywords = [
            'arthritis', 'rheumatoid', 'lupus', 'spondylitis', 'gout', 'myositis',
            'scleroderma', 'vasculitis', 'psoriatic', 'fibromyalgia', 'sjogren',
            'inflammatory', 'autoimmune', 'juvenile', 'dermatomyositis', 'polymyalgia',
            'ankylosing', 'osteoarthritis', 'spondyloarthritis', 'polymyositis',
            'polyarthritis', 'rheumatic', 'connective-tissue', 'systemic', 'disease',
            'condition', 'treatment', 'diagnosis', 'symptom', 'topic', 'chapter',
            # Add more specific rheumatology conditions/diseases
            'igg4', 'igg4-related', 'igg4-rd', 'still', 'sarcoidosis', 'anti-phospholipid',
            'giant-cell', 'takayasu', 'anca', 'granulomatosis', 'polyangiitis', 'wegener',
            'microscopic', 'eosinophilic', 'behcet', 'cryoglobulinemia', 'henoch', 'schonlein',
            'purpura', 'kawasaki', 'polyarteritis', 'nodosa', 'relapsing', 'polychondritis',
            'pmr', 'periodic', 'fever', 'familial', 'mediterranean', 'traps', 'hids', 'caps',
            'cppd', 'pseudogout', 'calcium', 'crystal', 'hydroxyapatite', 'basic', 'axial',
            'reactive', 'enteropathic', 'undifferentiated'
        ]
        
        # Reorder to prioritize disease/condition specific links
        prioritized_links = []
        normal_links = []
        
        for link in unique_links:
            if any(keyword in link.lower() for keyword in rheumatology_keywords):
                prioritized_links.append(link)
            else:
                normal_links.append(link)
                
        final_links = prioritized_links + normal_links
        
        logger.debug(f"Extracted {len(final_links)} unique links from {base_url} ({len(prioritized_links)} prioritized)")
        return final_links
    except Exception as e:
        logger.exception(f"Error extracting links: {str(e)}")
        return []

def _process_page(url, page_queue, visited, results, max_pages):
    """
    Process a single page, extract its content, and queue new links.
    
    Args:
        url (str): URL to process
        page_queue (queue.Queue): Queue of pages to process
        visited (set): Set of already visited URLs
        results (list): List to store results
        max_pages (int): Maximum number of pages to crawl
    """
    if len(visited) >= max_pages:
        return
    
    try:
        logger.debug(f"Processing page: {url}")
        
        # Fetch content
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            logger.warning(f"Failed to download: {url}")
            return
        
        # Extract text content with trafilatura
        text = trafilatura.extract(
            downloaded, 
            include_links=True, 
            include_images=False, 
            include_tables=True, 
            deduplicate=True, 
            no_fallback=False,
            favor_precision=False,
            include_comments=True  # Include comments which may have useful info
        )
        
        # Try alternate extraction if needed
        if not text or len(text.strip()) < 100:
            logger.debug("First extraction attempt yielded insufficient text, trying alternate parameters")
            text = trafilatura.extract(
                downloaded,
                include_comments=True,
                include_tables=True,
                no_fallback=False,
                target_language="en",
                include_formatting=True,  # Try to maintain some formatting
                include_anchors=True,     # Include anchor texts which are often navigation items
                favor_recall=True         # Favor recall over precision
            )
        
        # If still no content, try a third approach focused on menus and navigation
        if not text or len(text.strip()) < 100:
            logger.debug("Second extraction attempt failed, trying to extract navigation elements directly")
            try:
                # Parse the HTML and try to extract navigation elements manually
                soup = BeautifulSoup(downloaded, 'html.parser')
                
                # Focus on navigation/menu elements which are valuable for rheumatology sites
                nav_elements = []
                
                # Common navigation selectors 
                for selector in ['nav', '.nav', '.menu', '.navigation', '#nav', '#menu', 
                                 '.navbar', 'header', '.sidebar', '#sidebar', 'ul.menu',
                                 '.categories', '.topics', '.diseases', '.conditions',
                                 'ul.chapters', 'ul.sections', '[role="navigation"]']:
                    
                    if selector.startswith('.'):
                        els = soup.find_all(class_=selector[1:])
                    elif selector.startswith('#'):
                        el = soup.find(id=selector[1:])
                        if el:
                            els = [el]
                        else:
                            els = []
                    elif selector.startswith('['):
                        attr_name = selector.split('=')[0][1:]
                        attr_value = selector.split('=')[1].strip('"[]')
                        els = soup.find_all(attrs={attr_name: attr_value})
                    else:
                        els = soup.find_all(selector)
                    
                    nav_elements.extend(els)
                
                # Extract text from navigation elements with structure preserved
                nav_texts = []
                for nav in nav_elements:
                    # Extract text with some structure
                    items = []
                    for item in nav.find_all(['a', 'li', 'div', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                        if item.text.strip() and len(item.text.strip()) > 2:
                            items.append(item.text.strip())
                    
                    if items:
                        nav_texts.append(f"Menu/Navigation: {' | '.join(items)}")
                
                # Extract any headers which might contain useful subjects
                headers = []
                for h in soup.find_all(['h1', 'h2', 'h3']):
                    if h.text.strip() and len(h.text.strip()) > 3:
                        headers.append(f"Header: {h.text.strip()}")
                
                # If we found navigation elements or headers, use them as content
                if nav_texts or headers:
                    nav_content = "\n\n".join(nav_texts)
                    header_content = "\n\n".join(headers)
                    
                    # Extract title to include
                    title_tag = soup.find('title')
                    title_content = f"Title: {title_tag.text.strip()}" if title_tag else ""
                    
                    # Combine all elements
                    combined_text = "\n\n".join(filter(None, [title_content, nav_content, header_content]))
                    
                    if len(combined_text.strip()) > 50:
                        text = combined_text
                        logger.debug(f"Successfully extracted navigation and header elements: {len(text)} chars")
            except Exception as e:
                logger.exception(f"Error during manual extraction of navigation elements: {str(e)}")
        
        # Skip if no content was extracted after all attempts
        if not text or len(text.strip()) < 50:
            logger.warning(f"No significant content extracted from {url} after multiple attempts")
            return
        
        # Extract title
        title = extract_title(downloaded, url)
        
        # Generate citation
        citation = generate_website_citation(title, url)
        
        # Get page number for metadata
        page_num = len(visited) + 1
        
        # Process content
        chunks = []
        text_chunks = chunk_text(text, max_length=800, overlap=200)
        
        for i, chunk in enumerate(text_chunks):
            chunks.append({
                "text": chunk,
                "metadata": {
                    "source_type": "website",
                    "title": title,
                    "url": url,
                    "chunk_index": i,
                    "page_number": page_num,
                    "citation": citation,
                    "date_scraped": datetime.now().isoformat()
                }
            })
        
        # Add chunks to results
        if chunks:
            results.extend(chunks)
            logger.info(f"Added {len(chunks)} chunks from {url}")
        
        # Extract and queue new links for crawling
        if len(visited) < max_pages:
            links = _extract_links(downloaded, url)
            logger.debug(f"Found {len(links)} links on {url}")
            
            # Check for rheumatology-related terms to prioritize those links
            rheumatology_terms = ["rheumatoid", "arthritis", "lupus", "sle", "psoriatic", 
                                  "vasculitis", "scleroderma", "myositis", "igg4", "sjögren", 
                                  "sjogren", "gout", "ankylosing", "spondylitis", "inflammatory", 
                                  "connective tissue", "autoimmune", "rheumatic", "rheumatology",
                                  "dermatomyositis", "polymyositis", "systemic sclerosis"]
            
            # Find links that likely contain rheumatology content
            priority_links = []
            normal_links = []
            
            for link in links:
                # Skip already visited links
                if link in visited:
                    continue
                    
                # Check if the link URL contains any rheumatology terms
                link_lower = link.lower()
                if any(term in link_lower for term in rheumatology_terms):
                    priority_links.append(link)
                    logger.debug(f"Found priority rheumatology link: {link}")
                else:
                    normal_links.append(link)
            
            # First add priority links to the queue
            for link in priority_links:
                # Skip if queue is full
                if page_queue.full():
                    logger.debug(f"Queue full after processing priority links")
                    break
                    
                # Add to queue
                logger.debug(f"Queuing priority rheumatology link: {link}")
                page_queue.put(link)
            
            # Then add normal links
            for link in normal_links:
                # Skip if queue is full
                if page_queue.full():
                    logger.debug(f"Queue full, skipping remaining links")
                    break
                    
                # Add to queue
                logger.debug(f"Queuing normal link: {link}")
                page_queue.put(link)
    
    except Exception as e:
        logger.exception(f"Error processing page {url}: {str(e)}")

def scrape_website(url, max_pages=20, max_wait_time=60):
    """
    Scrape a website domain by crawling multiple pages and extract text content
    into chunks suitable for vector storage.
    
    Args:
        url (str): Starting URL to scrape
        max_pages (int): Maximum number of pages to crawl
        max_wait_time (int): Maximum time to wait for crawling in seconds
        
    Returns:
        list: List of dictionaries containing text chunks and metadata
    """
    logger.info(f"Starting web crawl from: {url} with max_pages={max_pages}")
    
    try:
        # Validate URL
        parsed_url = urllib.parse.urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise ValueError("Invalid URL format")
        
        # Initialize tracking structures
        visited = set()
        results = []
        page_queue = queue.Queue(maxsize=100)
        
        # Add starting URL to queue
        page_queue.put(url)
        
        # Check if this is a root domain without path
        parsed_url = urllib.parse.urlparse(url)
        if parsed_url.path == '' or parsed_url.path == '/':
            # For root domains, try to first check for topic and disease pages
            # These patterns work for rheumatology websites that often organize by disease/topic
            common_topic_paths = [
                '/topic/', '/disease/', '/chapter/', '/condition/', '/diseases/', 
                '/topics/', '/conditions/', '/chapters/', '/education/', 
                '/learn/', '/article/', '/articles/', '/info/'
            ]
            
            for path in common_topic_paths:
                potential_topic_page = f"{parsed_url.scheme}://{parsed_url.netloc}{path}"
                logger.debug(f"Adding potential topic page to queue: {potential_topic_page}")
                if potential_topic_page not in visited and not page_queue.full():
                    page_queue.put(potential_topic_page)
                    
            # Check for IgG4-RD specifically since the user mentioned it
            igg4_page = f"{parsed_url.scheme}://{parsed_url.netloc}/topic/igg4-related-disease/"
            if igg4_page not in visited and not page_queue.full():
                logger.debug(f"Adding specific IgG4-RD page to queue: {igg4_page}")
                page_queue.put(igg4_page)
        
        # Set up worker threads
        num_threads = min(5, max_pages)  # Use up to 5 threads
        threads = []
        
        # Event to signal threads to stop
        stop_event = threading.Event()
        
        # Define worker function
        def worker():
            while not stop_event.is_set():
                try:
                    # Get URL with timeout to allow checking stop_event
                    current_url = page_queue.get(timeout=0.5)
                    
                    # Skip if already visited
                    if current_url in visited:
                        page_queue.task_done()
                        continue
                    
                    # Mark as visited
                    visited.add(current_url)
                    
                    # Process the page
                    _process_page(current_url, page_queue, visited, results, max_pages)
                    
                    # Mark task as done
                    page_queue.task_done()
                    
                except queue.Empty:
                    # No more URLs to process
                    if page_queue.empty() or len(visited) >= max_pages:
                        return
                    continue
                except Exception as e:
                    logger.exception(f"Worker error: {str(e)}")
                    continue
        
        # Start worker threads
        for _ in range(num_threads):
            t = threading.Thread(target=worker)
            t.daemon = True
            t.start()
            threads.append(t)
        
        # Wait for completion or timeout
        start_time = time.time()
        while time.time() - start_time < max_wait_time:
            if page_queue.empty() or len(visited) >= max_pages:
                break
            time.sleep(0.5)
        
        # Signal threads to stop
        stop_event.set()
        
        # Wait for threads to finish (with timeout)
        for t in threads:
            t.join(timeout=1.0)
        
        # Log crawl stats
        logger.info(f"Web crawl complete: processed {len(visited)} pages, extracted {len(results)} chunks")
        
        # Process at least the initial URL
        if not results and url not in visited:
            logger.warning("No pages processed in multi-page crawl, falling back to single page processing")
            return _scrape_single_page(url)
        
        return results
        
    except Exception as e:
        logger.exception(f"Error during web crawl: {str(e)}")
        
        # Try to fall back to single page if crawl fails
        logger.warning("Falling back to single page processing after crawl failure")
        return _scrape_single_page(url)

def _scrape_single_page(url):
    """
    Scrape a single page as a fallback for the crawler.
    
    Args:
        url (str): URL to scrape
        
    Returns:
        list: List of dictionaries containing text chunks and metadata
    """
    logger.info(f"Scraping single page: {url}")
    
    try:
        # Fetch and extract content
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            raise Exception(f"Failed to download content from {url}")
        
        # Extract text content with trafilatura
        text = trafilatura.extract(
            downloaded, 
            include_links=True, 
            include_images=False, 
            include_tables=True, 
            deduplicate=True, 
            no_fallback=False,
            favor_precision=False,
            include_comments=True  # Include comments which may have useful info
        )
        
        # Try alternate extraction if needed
        if not text or len(text.strip()) < 100:
            logger.debug("First extraction attempt yielded insufficient text, trying alternate parameters")
            text = trafilatura.extract(
                downloaded,
                include_comments=True,
                include_tables=True,
                no_fallback=False,
                target_language="en",
                include_formatting=True,  # Try to maintain some formatting
                include_anchors=True,     # Include anchor texts which are often navigation items
                favor_recall=True         # Favor recall over precision
            )
        
        # If still no content, try a third approach focused on menus and navigation
        if not text or len(text.strip()) < 100:
            logger.debug("Second extraction attempt failed, trying to extract navigation elements directly")
            try:
                # Parse the HTML and try to extract navigation elements manually
                soup = BeautifulSoup(downloaded, 'html.parser')
                
                # Focus on navigation/menu elements which are valuable for rheumatology sites
                nav_elements = []
                
                # Common navigation selectors 
                for selector in ['nav', '.nav', '.menu', '.navigation', '#nav', '#menu', 
                                 '.navbar', 'header', '.sidebar', '#sidebar', 'ul.menu',
                                 '.categories', '.topics', '.diseases', '.conditions',
                                 'ul.chapters', 'ul.sections', '[role="navigation"]']:
                    
                    if selector.startswith('.'):
                        els = soup.find_all(class_=selector[1:])
                    elif selector.startswith('#'):
                        el = soup.find(id=selector[1:])
                        if el:
                            els = [el]
                        else:
                            els = []
                    elif selector.startswith('['):
                        attr_name = selector.split('=')[0][1:]
                        attr_value = selector.split('=')[1].strip('"[]')
                        els = soup.find_all(attrs={attr_name: attr_value})
                    else:
                        els = soup.find_all(selector)
                    
                    nav_elements.extend(els)
                
                # Extract text from navigation elements with structure preserved
                nav_texts = []
                for nav in nav_elements:
                    # Extract text with some structure
                    items = []
                    for item in nav.find_all(['a', 'li', 'div', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                        if item.text.strip() and len(item.text.strip()) > 2:
                            items.append(item.text.strip())
                    
                    if items:
                        nav_texts.append(f"Menu/Navigation: {' | '.join(items)}")
                
                # Extract any headers which might contain useful subjects
                headers = []
                for h in soup.find_all(['h1', 'h2', 'h3']):
                    if h.text.strip() and len(h.text.strip()) > 3:
                        headers.append(f"Header: {h.text.strip()}")
                
                # If we found navigation elements or headers, use them as content
                if nav_texts or headers:
                    nav_content = "\n\n".join(nav_texts)
                    header_content = "\n\n".join(headers)
                    
                    # Extract title to include
                    title_tag = soup.find('title')
                    title_content = f"Title: {title_tag.text.strip()}" if title_tag else ""
                    
                    # Combine all elements
                    combined_text = "\n\n".join(filter(None, [title_content, nav_content, header_content]))
                    
                    if len(combined_text.strip()) > 50:
                        text = combined_text
                        logger.debug(f"Successfully extracted navigation and header elements: {len(text)} chars")
            except Exception as e:
                logger.exception(f"Error during manual extraction of navigation elements: {str(e)}")
            
        if not text or len(text.strip()) < 50:
            raise Exception(f"No meaningful content extracted from {url} after multiple attempts")
        
        # Extract title
        title = extract_title(downloaded, url)
        
        # Generate citation
        citation = generate_website_citation(title, url)
        
        # Chunk content
        text_chunks = chunk_text(text, max_length=800, overlap=200)
        
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
                    "citation": citation,
                    "date_scraped": datetime.now().isoformat()
                }
            })
        
        logger.info(f"Created {len(chunks)} chunks from single page {url}")
        return chunks
        
    except Exception as e:
        logger.exception(f"Error scraping single page: {str(e)}")
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
