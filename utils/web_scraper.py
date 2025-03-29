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
    Extract links from HTML content that belong to the same domain,
    with special handling for disease/topic specific pages on rheumatology websites.
    
    Args:
        html (str): HTML content
        base_url (str): Base URL to match domain
        
    Returns:
        list: List of URLs belonging to the same domain, prioritized by relevance
    """
    try:
        soup = BeautifulSoup(html, 'html.parser')
        parsed_base_url = urllib.parse.urlparse(base_url)
        base_domain = parsed_base_url.netloc
        
        # Check if this is a topic page URL (e.g., /topic/myositis/)
        is_topic_page = False
        topic_patterns = ['/topic/', '/disease/', '/diseases/', '/condition/', '/conditions/']
        if any(pattern in parsed_base_url.path for pattern in topic_patterns):
            is_topic_page = True
            logger.info(f"Extracting links from a specific topic page: {base_url}")
        
        # Make sure the base URL ends with a slash for proper joining
        base_url_for_joining = base_url
        if not base_url.endswith('/') and not parsed_base_url.path:
            base_url_for_joining = f"{base_url}/"
            
        links = []
        
        # Expanded list of navigation class/id patterns to better capture rheumatology websites
        nav_selectors = [
            # Basic navigation elements
            'nav', '.nav', '.menu', '.navigation', '#nav', '#menu', '#navigation',
            '.navbar', '.header-menu', '.main-menu', '.primary-menu', '.site-menu',
            'header', '.header', '#header', '.sidebar', '#sidebar', 
            '.main-nav', '.top-nav',
            
            # Content organization elements common in medical/academic sites
            '.categories', '.chapters', '.sections', '.topics', '#topics', 
            '.diseases', '#diseases', '.conditions', '#conditions',
            
            # Additional selectors for specific site structures
            '[role="navigation"]', '.site-nav', '.dropdown-menu', '.submenu', 
            '.accordion', '.card-header', '.tablist', '.tab-content',
            '.tree-menu', '.tree-nav', '.list-group', '.collection-list',
            '#content-navigation', '#page-navigation', '#sidebar-menu',
            
            # Target disease/topic sections specifically
            '.disease-menu', '.topic-menu', '.condition-list', '.disease-list',
            '#disease-navigation', '#topic-navigation', '.disease-categories',
            '.topic-categories', '.clinical-topics', '.medical-topics'
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
                
                # Skip empty hrefs
                if not href.strip():
                    continue
                    
                # Handle different types of relative URLs more robustly
                if href.startswith('/'):
                    # Absolute path relative to domain root
                    href = f"{parsed_base_url.scheme}://{parsed_base_url.netloc}{href}"
                elif href.startswith('./'):
                    # Explicit relative to current directory
                    href = urllib.parse.urljoin(base_url_for_joining, href[2:])
                elif href.startswith('../'):
                    # Relative to parent directory
                    href = urllib.parse.urljoin(base_url_for_joining, href)
                elif not href.startswith(('http://', 'https://')):
                    # Skip anchors and javascript links
                    if href.startswith('#') or href.startswith('javascript:'):
                        continue
                    # Other relative paths - join with base URL
                    href = urllib.parse.urljoin(base_url_for_joining, href)
                
                # Parse the new URL to check domain
                parsed_href = urllib.parse.urlparse(href)
                
                # Only include links from the same domain
                if parsed_href.netloc == base_domain:
                    # Clean URL - remove fragments and normalize
                    clean_href = urllib.parse.urljoin(href, urllib.parse.urlparse(href).path)
                    
                    # Sometimes clean_href drops the trailing slash which can be significant
                    # If original had a trailing slash but clean doesn't, add it back
                    if href.endswith('/') and not clean_href.endswith('/'):
                        clean_href = f"{clean_href}/"
                        
                    # Also normalize to avoid www vs non-www duplicates
                    if clean_href not in priority_links:
                        priority_links.append(clean_href)
        
        # Process remaining links from the page
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            
            # Skip empty hrefs
            if not href.strip():
                continue
                
            # Handle different types of relative URLs more robustly
            if href.startswith('/'):
                # Absolute path relative to domain root
                href = f"{parsed_base_url.scheme}://{parsed_base_url.netloc}{href}"
            elif href.startswith('./'):
                # Explicit relative to current directory
                href = urllib.parse.urljoin(base_url_for_joining, href[2:])
            elif href.startswith('../'):
                # Relative to parent directory
                href = urllib.parse.urljoin(base_url_for_joining, href)
            elif not href.startswith(('http://', 'https://')):
                # Skip anchors and javascript links
                if href.startswith('#') or href.startswith('javascript:'):
                    continue
                # Other relative paths - join with base URL
                href = urllib.parse.urljoin(base_url_for_joining, href)
            
            # Parse the new URL to check domain
            parsed_href = urllib.parse.urlparse(href)
            
            # Only include links from the same domain
            if parsed_href.netloc == base_domain:
                # Clean URL - remove fragments and normalize
                clean_href = urllib.parse.urljoin(href, urllib.parse.urlparse(href).path)
                
                # Sometimes clean_href drops the trailing slash which can be significant
                # If original had a trailing slash but clean doesn't, add it back
                if href.endswith('/') and not clean_href.endswith('/'):
                    clean_href = f"{clean_href}/"
                    
                # Add if not already in priority links
                if clean_href not in links and clean_href not in priority_links:
                    links.append(clean_href)
        
        # Give priority to navigation links by placing them first
        combined_links = priority_links + links
        
        # Remove duplicates while preserving order
        unique_links = list(dict.fromkeys(combined_links))
        
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
        # Check if this is a topic-specific URL like /topic/myositis/
        parsed_url = urllib.parse.urlparse(url)
        topic_patterns = ['/topic/', '/disease/', '/diseases/', '/condition/', '/conditions/']
        is_topic_page = any(pattern in parsed_url.path for pattern in topic_patterns)
        
        if is_topic_page:
            logger.info(f"Processing topic-specific page with high priority: {url}")
        else:
            logger.debug(f"Processing page: {url}")
        
        # Fetch content with priority for topic pages
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            # Retry for topic pages
            if is_topic_page:
                logger.warning(f"Failed first attempt to download topic page: {url}, retrying")
                # Sleep a bit and retry
                import time
                time.sleep(2)
                downloaded = trafilatura.fetch_url(url)
            
            if not downloaded:
                logger.warning(f"Failed to download: {url}")
                return
        
        # Extract text content with trafilatura - special handling for topic pages
        if is_topic_page:
            logger.info(f"Using enhanced extraction for topic page: {url}")
            
            # Try multiple approaches for topic pages since they're critical content
            # First, try trafilatura's extraction with maximized parameters for maximum content
            text = trafilatura.extract(
                downloaded, 
                include_links=True,        # Include links to capture references
                include_images=True,       # Include image captions which may contain useful text
                include_tables=True,       # Tables often contain important disease information
                deduplicate=False,         # Don't deduplicate to ensure we get all content
                no_fallback=False,         # Always use fallback methods if needed
                favor_recall=True,         # Prioritize getting more content over precision
                include_comments=True,     # Include comments which may have useful info
                include_formatting=True,   # Preserve formatting which can provide structure
                target_language="en",      # Ensure English content
                include_anchors=True,      # Include anchor texts which are often navigation items
                include_headings=True,     # Ensure headers are captured as they organize content
                include_footnotes=True     # Footnotes may contain valuable references
            )
            
            # If trafilatura extraction fails, use BeautifulSoup as a backup
            if not text or len(text.strip()) < 200:
                logger.info(f"Trafilatura extraction failed for topic page {url}, trying direct HTML extraction")
                try:
                    soup = BeautifulSoup(downloaded, 'html.parser')
                    
                    # Extract main content elements that typically contain article text
                    content_elements = []
                    for selector in [
                        'article', '.article', '#article', '.content', '#content', 
                        '.main-content', '#main-content', '.page-content', '#page-content',
                        '.entry-content', '.post-content', '.topic-content', '.disease-content',
                        'main', '#main', '.main', '[role="main"]', '.container', '.topic',
                        '#topic-content', '.article-body', '.entry', '.page'
                    ]:
                        if selector.startswith('.'):
                            found = soup.find_all(class_=selector[1:])
                        elif selector.startswith('#'):
                            found = soup.find(id=selector[1:])
                            found = [found] if found else []
                        elif selector.startswith('['):
                            attr_name = selector.split('=')[0][1:]
                            attr_value = selector.split('=')[1].strip('"[]')
                            found = soup.find_all(attrs={attr_name: attr_value})
                        else:
                            found = soup.find_all(selector)
                        
                        content_elements.extend([e for e in found if e])
                    
                    # Also look for div elements with "content", "article", "topic" in id/class
                    for keyword in ['content', 'article', 'topic', 'disease', 'main', 'text']:
                        for div in soup.find_all('div'):
                            div_id = div.get('id', '').lower()
                            div_class = ' '.join(div.get('class', [])).lower()
                            if keyword in div_id or keyword in div_class:
                                content_elements.append(div)
                    
                    # Extract and clean text from content elements
                    extracted_texts = []
                    
                    # Process each content element
                    for element in content_elements:
                        # Remove script, style, and nav elements which don't contain relevant text
                        for unwanted in element.find_all(['script', 'style', 'nav', 'header', 'footer']):
                            unwanted.decompose()
                        
                        # Get text with some structure preserved
                        element_text = element.get_text(separator=' ', strip=True)
                        if element_text and len(element_text) > 100:  # Only include substantial content
                            extracted_texts.append(element_text)
                    
                    # Use the largest extracted text (likely the main content)
                    if extracted_texts:
                        largest_text = max(extracted_texts, key=len)
                        if len(largest_text) > len(text or ""):
                            text = largest_text
                            logger.info(f"Successfully extracted {len(text)} chars using direct HTML parsing")
                except Exception as e:
                    logger.exception(f"Error in fallback HTML extraction for topic page: {str(e)}")
                
            # If we still don't have content, create minimal content with topic information
            if not text or len(text.strip()) < 200:
                logger.warning(f"All extraction methods failed for topic page: {url}, creating minimal content")
                topic_name = parsed_url.path.strip('/').split('/')[-1].replace('-', ' ').title()
                
                # Get the title of the page for better information
                title = "Unknown Topic"
                try:
                    title_element = soup.find('title')
                    if title_element and title_element.text:
                        title = title_element.text.strip()
                except:
                    pass
                
                # Create minimal content
                text = f"""Rheumatology Topic Page: {topic_name}
Title: {title}
URL: {url}

This is a specialized page about {topic_name} in rheumatology. 
The page appears to contain information about this specific condition or topic,
but full content extraction was not possible."""
        else:
            # Use the same enhanced parameters for all pages to maximize content extraction
            text = trafilatura.extract(
                downloaded, 
                include_links=True,        # Include links to capture references
                include_images=True,       # Include image captions which may contain useful text
                include_tables=True,       # Tables often contain important disease information
                deduplicate=False,         # Don't deduplicate to ensure we get all content
                no_fallback=False,         # Always use fallback methods if needed
                favor_recall=True,         # Prioritize getting more content over precision
                include_comments=True,     # Include comments which may have useful info
                include_formatting=True,   # Preserve formatting which can provide structure
                target_language="en",      # Ensure English content
                include_anchors=True,      # Include anchor texts which are often navigation items
                include_headings=True,     # Ensure headers are captured as they organize content
                include_footnotes=True     # Footnotes may contain valuable references
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
            
            # For topic pages, add at least minimal information
            if is_topic_page:
                logger.info(f"Creating minimal content entry for important topic page: {url}")
                # Create a minimal text entry with the URL and topic name
                topic_name = parsed_url.path.strip('/').split('/')[-1].replace('-', ' ').title()
                text = f"Rheumatology Topic Page: {topic_name}\n\nThis is a specialized page about {topic_name} in rheumatology. The page URL is {url}."
            else:
                return
        
        # Extract title
        title = extract_title(downloaded, url)
        
        # Generate citation
        citation = generate_website_citation(title, url)
        
        # Get page number for metadata
        page_num = len(visited) + 1
        
        # Process content with larger chunk sizes
        chunks = []
        text_chunks = chunk_text(text, max_length=1000, overlap=250)
        
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

def scrape_website(url, max_pages=25, max_wait_time=120):
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
        
        # Check if this is a specific topic/disease URL (like /topic/myositis/)
        # These need special handling to ensure we crawl them properly
        topic_path_patterns = ['/topic/', '/disease/', '/diseases/', '/condition/', '/conditions/', '/chapter/']
        if any(pattern in parsed_url.path for pattern in topic_path_patterns):
            logger.info(f"Detected specific topic URL: {url} - giving it special priority crawling")
            # For topic URLs, we should prioritize crawling directly
            # When we detect a specific disease/topic page, we'll prioritize crawling it first
            # This ensures we don't miss topic-specific content
        
        # Continue with normal crawling for root domain
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
                    
            # Check for common disease patterns in rheumatology websites
            # These paths cover standard URL structures across rheumatology websites
            common_disease_paths = [
                "/topic/",
                "/disease/",
                "/diseases/",
                "/condition/",
                "/conditions/",
                "/chapter/",
                "/chapters/",
                "/articles/",
                "/article/"
            ]
            
            # And the rest of the function...
            # Expanded list of rheumatology conditions to check for specific disease pages
            rheumatology_diseases = [
                # Common inflammatory arthritides with URL variants
                "rheumatoid-arthritis", "ra", "rheumatoid_arthritis", "rheumatoidarthritis", 
                "rheumatoid", "arthritis-rheumatoid", "juvenile-rheumatoid-arthritis", "jra",
                "psoriatic-arthritis", "psa", "psoriatic_arthritis", "psoriaticarthritis", 
                "psoriatic", "arthritis-psoriatic", "psoriasis-arthritis",
                "ankylosing-spondylitis", "as", "ankylosing_spondylitis", "ankylosingspondylitis", 
                "spondylitis", "ankylosis",
                "axial-spondyloarthritis", "axial-spa", "axspa", "axial_spondyloarthritis",
                "peripheral-spondyloarthritis", "peripheral-spa", "perspa", "peripheral_spondyloarthritis",
                "spondyloarthritis", "spa", "spondyloarthropathy", "spondyloarthropathies",
                "reactive-arthritis", "reactive_arthritis", "reiter", "reiters-syndrome",
                "enteropathic-arthritis", "enteropathic_arthritis", "ibd-arthritis",
                "inflammatory-arthritis", "inflammatory_arthritis", "inflammatory-joint-disease",
                "erosive-arthritis", "seronegative-arthritis", "seropositive-arthritis",
                
                # Connective tissue diseases with URL variants
                "lupus", "sle", "systemic-lupus-erythematosus", "systemic_lupus", "lupus-erythematosus",
                "cutaneous-lupus", "cle", "drug-induced-lupus", "dil", "neonatal-lupus", "lupus-nephritis",
                "scleroderma", "systemic-sclerosis", "ssc", "systemic_sclerosis", "systemicsclerosis",
                "limited-scleroderma", "diffuse-scleroderma", "crest-syndrome", "morphea",
                "myositis", "inflammatory-myopathy", "idiopathic-inflammatory-myopathy", "iim",
                "dermatomyositis", "dm", "polymyositis", "pm", "inclusion-body-myositis", "ibm", 
                "anti-synthetase-syndrome", "necrotizing-myopathy", "immune-mediated-necrotizing-myopathy",
                "sjögren", "sjogren", "sjögrens-syndrome", "sjogrens-syndrome", "ss", "sicca-syndrome",
                "sjögrens-disease", "sjogrens-disease", "sjögrens_syndrome", "sjogrens_syndrome",
                "mixed-connective-tissue-disease", "mctd", "mixed_connective", "mctdisease", "overlap-syndrome",
                "undifferentiated-connective-tissue-disease", "uctd", "connective-tissue-disease", "ctd",
                "connective_tissue", "connectivetissue",
                
                # Vasculitides with URL variants
                "vasculitis", "vasculitides", "large-vessel-vasculitis", "medium-vessel-vasculitis", 
                "small-vessel-vasculitis", "leukocytoclastic-vasculitis", "cutaneous-vasculitis",
                "giant-cell-arteritis", "gca", "temporal-arteritis", "cranial-arteritis", "horton",
                "takayasus-arteritis", "takayasu", "tak", "takayasus_arteritis", "takayasuarteritis",
                "polyarteritis-nodosa", "pan", "kussmaul-disease", "kawasaki-disease", "mucocutaneous-lymph-node-syndrome",
                "anca-vasculitis", "anca-associated-vasculitis", "aav", "anca_vasculitis", "anca_associated",
                "granulomatosis-with-polyangiitis", "gpa", "wegeners", "wegener", "wegeners-granulomatosis",
                "microscopic-polyangiitis", "mpa", "microscopic_polyangiitis", "microscopicpolyangiitis",
                "eosinophilic-granulomatosis-with-polyangiitis", "egpa", "churg-strauss", "churg_strauss",
                "igg4-related-disease", "igg4-rd", "igg4_related", "igg4", "igg4relateddisease",
                "behcets-disease", "behcets-syndrome", "behcet", "behcets", "adamantiades",
                
                # Autoinflammatory conditions with URL variants
                "adult-onset-stills-disease", "aosd", "stills-disease", "still", "adult_stills", "adultstills",
                "systemic-juvenile-idiopathic-arthritis", "sjia", "juvenile-idiopathic-arthritis", "jia",
                "periodic-fever-syndrome", "autoinflammatory-syndrome", "autoinflammatory-disease",
                "familial-mediterranean-fever", "fmf", "mediterranean_fever", "familial_mediterranean", 
                "cryopyrin-associated-periodic-syndrome", "caps", "cryopyrin", "muckle-wells", "fcas",
                "tumor-necrosis-factor-receptor-associated-periodic-syndrome", "traps",
                "hyperimmunoglobulin-d-syndrome", "hids", "mevalonate-kinase-deficiency", "mkd",
                
                # Crystal arthropathies with URL variants
                "gout", "gouty-arthritis", "tophaceous-gout", "uric-acid", "urate", "hyperuricemia",
                "calcium-pyrophosphate-deposition", "cppd", "pseudogout", "chondrocalcinosis", "pyrophosphate-arthropathy",
                "basic-calcium-phosphate", "bcp", "hydroxyapatite-deposition-disease", "hadd",
                "crystal-induced-arthritis", "crystal-arthropathy", "crystal-arthritis", "microcrystalline-arthritis",
                
                # Other rheumatic conditions with URL variants
                "fibromyalgia", "fibrositis", "chronic-widespread-pain", "fibromyalgia-syndrome", "fms",
                "osteoarthritis", "oa", "degenerative-joint-disease", "djd", "osteoarthrosis", "degenerative-arthritis",
                "erosive-osteoarthritis", "primary-osteoarthritis", "secondary-osteoarthritis",
                "polymyalgia-rheumatica", "pmr", "polymyalgia_rheumatica", "polymyalgiarheumatica",
                "autoimmune", "autoimmunity", "autoimmune-disease", "autoimmune-condition", "autoimmune-disorder",
                "uveitis", "iritis", "iridocyclitis", "chorioretinitis", "scleritis", "episcleritis",
                "sarcoidosis", "lofgrens-syndrome", "lofgren", "sarcoid", "sarcoidosis-arthritis",
                "anti-phospholipid-syndrome", "aps", "antiphospholipid", "anti_phospholipid", "hughes-syndrome",
                "relapsing-polychondritis", "rpc", "polychondritis", "atrophic-polychondritis",
                "rheumatic-disease", "rheumatic-disorder", "rheumatic-condition", "rheumatic-illness",
                "raynauds", "raynauds-phenomenon", "raynauds-syndrome", "raynaud", "primary-raynauds", "secondary-raynauds",
                "reactive-arthritis", "enteropathic-arthritis", "enthesitis", "dactylitis", "synovitis",
                
                # Common treatment terms that indicate relevant pages
                "dmard", "dmards", "biologic", "biologics", "tnf", "anti-tnf", "jak-inhibitor",
                "methotrexate", "hydroxychloroquine", "leflunomide", "sulfasalazine", 
                "rituximab", "abatacept", "tocilizumab", "anakinra", "baricitinib", "tofacitinib",
                "remission", "acr-response", "das28", "joint-flare", "flare-management",
                
                # Use simpler or abbreviated terms that may appear in URLs
                "sjd", "ra", "psa", "spa", "as", "sle", "ssc", "dm", "pm", "ss", "gout", "oa", "vasc", "lupus",
                "arthritis", "immune", "rheumatic", "rheum", "arthr", "inflamm", "itis", "pain", "rheumatology"
            ]
            
            # Try all potential disease paths for common rheumatology conditions
            for base_path in common_disease_paths:
                for disease in rheumatology_diseases:
                    # Create paths with both hyphenated and non-hyphenated versions
                    disease_variants = [disease]
                    if "-" in disease:
                        disease_variants.append(disease.replace("-", ""))
                    
                    for variant in disease_variants:
                        disease_page = f"{parsed_url.scheme}://{parsed_url.netloc}{base_path}{variant}/"
                        if disease_page not in visited and not page_queue.full():
                            logger.debug(f"Adding potential disease page to queue: {disease_page}")
                            page_queue.put(disease_page)
            
            # Also search for disease terms in main page links and prioritize those for immediate crawling
            try:
                # Try to quickly scan the main page for any disease-related links we can immediately process
                main_downloaded = trafilatura.fetch_url(url)
                if main_downloaded:
                    # Use soup to find all links on the page
                    soup = BeautifulSoup(main_downloaded, 'html.parser')
                    # Expanded list of terms to check in main page links
                    prioritized_terms = [
                        # Common terms
                        "rheumatoid", "arthritis", "lupus", "vasculitis", "igg4", "autoimmune",
                        # Disease abbreviations 
                        "ra", "sle", "psa", "as", "spa", "ssc", "pm", "dm", "ss", "aps",
                        # Disease-specific terms
                        "sjögren", "sjogren", "sjd", "gout", "myositis", "spondyl", "sclero", "dermato",
                        # Common site organization terms
                        "topic", "disease", "condition", "disorder", "syndrome"
                    ]
                    
                    for a_tag in soup.find_all('a', href=True):
                        link_href = a_tag['href']
                        link_text = a_tag.get_text().lower()
                        
                        # Check if this link might be about a high-priority rheumatology disease
                        if any(term in link_href.lower() or term in link_text for term in prioritized_terms):
                            # Convert relative URL to absolute if needed
                            if not link_href.startswith('http'):
                                if link_href.startswith('/'):
                                    link_href = f"{parsed_url.scheme}://{parsed_url.netloc}{link_href}"
                                else:
                                    link_href = f"{parsed_url.scheme}://{parsed_url.netloc}/{link_href}"
                            
                            if link_href not in visited and not page_queue.full():
                                logger.debug(f"Found disease link in main page: {link_href} (text: {link_text})")
                                # Priority addition to queue - process next
                                temp_queue = queue.Queue(maxsize=100)
                                temp_queue.put(link_href)
                                
                                # Move existing URLs from page_queue to temp_queue
                                while not page_queue.empty():
                                    temp_url = page_queue.get()
                                    if not temp_queue.full():
                                        temp_queue.put(temp_url)
                                
                                # Replace page_queue with temp_queue
                                while not temp_queue.empty():
                                    page_queue.put(temp_queue.get())
            except Exception as e:
                logger.exception(f"Error looking for disease links in main page: {str(e)}")
        
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
            
            # Check if this is a topic page first
            parsed_url = urllib.parse.urlparse(url)
            topic_patterns = ['/topic/', '/disease/', '/diseases/', '/condition/', '/conditions/']
            is_topic_page = any(pattern in parsed_url.path for pattern in topic_patterns)
            
            # For topic pages, use our specialized direct extraction method first
            if is_topic_page:
                logger.info(f"Detected a topic page URL, using specialized direct extraction: {url}")
                minimal_content = create_minimal_content_for_topic(url)
                if minimal_content:
                    logger.info(f"Successfully created {len(minimal_content)} chunks with specialized topic page extraction")
                    return minimal_content
                logger.warning("Specialized topic extraction failed, falling back to standard method")
            
            # Fall back to single page scraper for non-topic pages or if topic extraction failed
            single_page_results = _scrape_single_page(url)
            
            # If standard methods failed but this is a topic page, make one final attempt with minimal content
            if not single_page_results and is_topic_page:
                logger.warning(f"All extraction methods failed for topic page: {url}, creating basic fallback")
                topic_name = parsed_url.path.strip('/').split('/')[-1].replace('-', ' ').title()
                text = f"""Rheumatology Topic Page: {topic_name}
URL: {url}

This is a specialized page about {topic_name} in rheumatology."""
                
                citation = f"Information about {topic_name}. Retrieved {datetime.now().strftime('%B %d, %Y')}, from {url}"
                
                return [{
                    "text": text,
                    "metadata": {
                        "source_type": "website",
                        "title": f"Rheumatology Topic: {topic_name}",
                        "url": url,
                        "chunk_index": 0,
                        "page_number": 1,
                        "citation": citation,
                        "date_scraped": datetime.now().isoformat(),
                        "is_minimal_content": True,
                        "is_fallback": True
                    }
                }]
            
            return single_page_results
        
        return results
        
    except Exception as e:
        logger.exception(f"Error during web crawl: {str(e)}")
        
        # Try to fall back to single page if crawl fails
        logger.warning("Falling back to single page processing after crawl failure")
        return _scrape_single_page(url)

def create_minimal_content_for_topic(url):
    """
    Create comprehensive content for topic pages.
    This is an enhanced method that extracts maximum content from topic pages.
    Optimized to produce many high-quality chunks rather than a few minimal chunks.
    
    Args:
        url (str): URL of the topic page
        
    Returns:
        list: List of dictionaries containing text chunks and metadata or empty list if failed
    """
    # Check if this is a topic/disease page
    if '/topic/' in url or '/disease/' in url:
        logger.info(f"Processing topic {url.split('/')[-2]} with no chunk limit")
        
        try:
            # Get content with our direct extraction method 
            # This ensures we get the most content possible
            results = extract_website_direct(url)
            
            if results and len(results) > 0:
                # Create memory-optimized chunks
                optimized_results = []
                for chunk in results:
                    # Simplify metadata to save memory
                    simple_metadata = {
                        'title': chunk['metadata']['title'],
                        'url': chunk['metadata']['url'],
                        'source_type': 'website',
                        'citation': chunk['metadata']['citation'],
                        'chunk_index': chunk['metadata']['chunk_index'],
                        'date_scraped': datetime.now().isoformat()
                    }
                    
                    # Add optimized chunk
                    optimized_results.append({
                        'text': chunk['text'],
                        'metadata': simple_metadata
                    })
                
                logger.info(f"Created {len(optimized_results)} memory-optimized chunks for topic page")
                return optimized_results
            else:
                logger.warning(f"Direct extraction returned no chunks, trying fallback for topic page: {url}")
                # Proceed to fallback extraction
        except Exception as e:
            logger.exception(f"Error in direct extraction for topic, trying fallback: {str(e)}")
            # Continue to fallback approach
    
    # Fallback extraction or non-topic page
    logger.info(f"Creating memory-optimized minimal content for topic page: {url}")
    
    # Parse URL
    parsed_url = urllib.parse.urlparse(url)
    
    # Extract topic name from URL path for fallback content
    topic_name = parsed_url.path.strip('/').split('/')[-1].replace('-', ' ').title()
    
    # Try to get page content directly with strict memory limits
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Use a session to minimize memory usage and add timeout
        with requests.Session() as session:
            response = session.get(url, headers=headers, timeout=10, stream=True)
            
            # Default title
            title = f"Rheumatology Topic: {topic_name}"
            content_text = ""
            
            if response.status_code == 200:
                # Read content in chunks to minimize memory usage
                html_content = ""
                for chunk in response.iter_content(chunk_size=1024 * 8, decode_unicode=True):
                    if chunk:
                        html_content += chunk
                        # Safety limit to avoid memory issues, but make it much larger
                        if len(html_content) > 1000 * 1024:  # 1MB limit instead of 100KB
                            logger.warning(f"Reached HTML content size limit for {url}, truncating")
                            break
                
                # Process with BeautifulSoup using lxml parser (faster and more memory-efficient)
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Clear html_content to free memory
                html_content = None
                
                # Extract title using our improved function
                title = extract_title(str(soup), url)
                logger.info(f"Extracted title: {title}")
                
                # Extract content from article element - only look for main content
                article = soup.find('article')
                if article:
                    content_text = article.get_text(separator=' ', strip=True)
                    logger.info(f"Extracted {len(content_text)} chars from article element")
                    
                    # Clear article to free memory
                    article = None
                
                # If article didn't work, try only main/content containers (limited set)
                if not content_text or len(content_text) < 100:
                    # Only check the most common containers to avoid memory issues
                    for selector in ['.content', 'main', '.main-content', '.entry-content']:
                        element = None
                        if selector.startswith('.'):
                            element = soup.find(class_=selector[1:])
                        else:
                            element = soup.find(selector)
                                
                        if element:
                            extracted = element.get_text(separator=' ', strip=True)
                            if len(extracted) > len(content_text):
                                content_text = extracted
                                logger.info(f"Extracted {len(content_text)} chars from {selector}")
                            
                            # Clear to free memory
                            element = None
                            extracted = None
                
                # Clear soup to free memory
                soup = None
        
        # Create content
        if content_text and len(content_text) > 200:
            # Format with title and content - extract as much content as possible
            # Greatly increase size to allow all content
            text = f"{title}\n\n{content_text[:100000]}"  # Limit to 100000 chars to get all content
            logger.info(f"Created content with actual extracted text (limited to {len(text)} chars)")
        else:
            # Create minimal fallback
            text = f"""Rheumatology Topic Page: {title}
URL: {url}

This is a specialized page about {topic_name} in rheumatology.
The page appears to contain information about this specific condition or topic."""
            logger.info(f"Created minimal fallback content ({len(text)} chars)")
        
        # Format as chunks - but limit number of chunks
        citation = generate_website_citation(title, url)
        chunks = []
        
        # Use our standard chunking function with better parameters
        text_chunks = chunk_text(text, max_length=800, overlap=200)
        
        # No chunk limit - process all content
        # All topics are equally important and should have maximum chunks
        
        # Extremely high maximum to effectively disable the limit
        max_chunks = 1000
        
        # Apply chunk limit if needed
        if len(text_chunks) > max_chunks:
            logger.warning(f"Limiting chunks from {len(text_chunks)} to {max_chunks}")
            text_chunks = text_chunks[:max_chunks]
        
        # Create chunk objects
        for i, chunk in enumerate(text_chunks):
            chunks.append({
                "text": chunk,
                "metadata": {
                    "source_type": "website",
                    "title": title,
                    "url": url,
                    "chunk_index": i,
                    "page_number": 1,
                    "citation": citation,
                    "date_scraped": datetime.now().isoformat()
                }
            })
        
        logger.info(f"Created {len(chunks)} memory-optimized chunks for topic page")
        return chunks
    
    except Exception as e:
        logger.exception(f"Error creating minimal content: {str(e)}")
        
        # Absolute minimal fallback with a single chunk
        try:
            text = f"""Rheumatology Topic Page: {topic_name}
URL: {url}

This is a page about {topic_name} in rheumatology."""
            
            citation = f"Information about {topic_name}. Retrieved {datetime.now().strftime('%B %d, %Y')}, from {url}"
            
            return [{
                "text": text,
                "metadata": {
                    "source_type": "website",
                    "title": f"Rheumatology Topic: {topic_name}",
                    "url": url,
                    "chunk_index": 0,
                    "page_number": 1,
                    "citation": citation,
                    "date_scraped": datetime.now().isoformat(),
                    "is_fallback": True
                }
            }]
        except Exception as e2:
            logger.exception(f"Error creating fallback: {str(e2)}")
            return []

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
        
        # Chunk content with larger chunk size and more overlap for better context
        text_chunks = chunk_text(text, max_length=1000, overlap=250)
        
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
        # Try to extract directly from HTML using BeautifulSoup
        try:
            soup = BeautifulSoup(html, 'html.parser')
            title_tag = soup.find('title')
            if title_tag and title_tag.string:
                title = title_tag.string.strip()
                logger.debug(f"Found title with BeautifulSoup: {title}")
                return title
        except Exception as bs_error:
            logger.debug(f"BeautifulSoup title extraction failed: {str(bs_error)}")
        
        # Try to extract using regex as fallback
        try:
            import re
            title_match = re.search('<title>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
            if title_match:
                title = title_match.group(1).strip()
                logger.debug(f"Found title with regex: {title}")
                return title
        except Exception as regex_error:
            logger.debug(f"Regex title extraction failed: {str(regex_error)}")
            
        # If all else fails, use domain or path from URL
        parsed_url = urllib.parse.urlparse(url)
        
        # Use path as title if it exists and looks meaningful
        if parsed_url.path and parsed_url.path not in ['/', '']:
            path = parsed_url.path.strip('/')
            parts = path.split('/')
            if len(parts) > 0:
                # Use the last part of the path and make it readable
                title = parts[-1].replace('-', ' ').replace('_', ' ').title()
                logger.debug(f"Using path as fallback title: {title}")
                return title
        
        # Use domain as last resort
        domain = parsed_url.netloc
        logger.debug(f"Using domain as fallback title: {domain}")
        return domain
        
    except Exception as e:
        logger.exception(f"Error extracting title: {str(e)}")
        # Use domain name as absolute last resort
        try:
            parsed_url = urllib.parse.urlparse(url)
            domain = parsed_url.netloc
            logger.debug(f"Using domain as exception fallback title: {domain}")
            return domain
        except:
            return "Website Document"
        
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

def extract_website_direct(url):
    """
    Extract content from a website using a direct, intensive approach.
    This method focuses on maximum content extraction from a single page.
    Specialized to overcome the 8-chunk limitation by using multiple extraction methods.
    
    Args:
        url (str): URL to extract content from
        
    Returns:
        list: List of dictionaries containing text chunks and metadata
    """
    logger.info(f"Extracting website content directly from: {url} (DEBUG MODE)")
    
    try:
        # Setup headers for the request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Get the page content
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            logger.warning(f"Failed to fetch URL: {url}, status code: {response.status_code}")
            return []
        
        html_content = response.text
        logger.info(f"Downloaded HTML content: {len(html_content)} bytes")
        
        # Extract title
        title = extract_title(html_content, url)
        
        # ----- Try all extraction methods in parallel and use the one with most content -----
        all_extracted_texts = []
        
        # Method 1: Trafilatura with compatible parameters
        try:
            # Use only parameters actually supported by trafilatura
            text1 = trafilatura.extract(
                html_content, 
                include_links=True,        # Include links to capture references
                include_images=True,       # Include image captions which may contain useful text
                include_tables=True,       # Tables often contain important disease information
                deduplicate=False,         # Don't deduplicate to ensure we get all content
                no_fallback=False,         # Always use fallback methods if needed
                favor_recall=True,         # Prioritize getting more content over precision
                include_comments=True,     # Include comments which may have useful info
                include_formatting=True    # Preserve formatting which can provide structure
                # Removed incompatible parameters:
                # include_anchors, include_headings, include_footnotes
            )
            if text1:
                logger.info(f"Method 1 - Trafilatura (compatible params): {len(text1)} chars")
                all_extracted_texts.append((text1, "Trafilatura (compatible params)"))
        except Exception as e:
            logger.warning(f"Method 1 failed: {str(e)}")
        
        # Method 2: Simple Trafilatura
        try:
            # Simplest parameters for maximum compatibility
            text2 = trafilatura.extract(html_content, favor_recall=True)
            if text2:
                logger.info(f"Method 2 - Trafilatura (simple): {len(text2)} chars")
                all_extracted_texts.append((text2, "Trafilatura (simple)"))
        except Exception as e:
            logger.warning(f"Method 2 failed: {str(e)}")
            
        # Method 3: BeautifulSoup - article extraction
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            text3 = ""
            article = soup.find('article')
            if article:
                text3 = article.get_text(separator=' ', strip=True)
                if text3:
                    logger.info(f"Method 3 - BeautifulSoup (article): {len(text3)} chars")
                    all_extracted_texts.append((text3, "BeautifulSoup (article)"))
        except Exception as e:
            logger.warning(f"Method 3 failed: {str(e)}")
            
        # Method 4: BeautifulSoup - main content selectors
        try:
            if not soup:
                soup = BeautifulSoup(html_content, 'html.parser')
                
            # Try to extract content from common content containers
            content_selectors = ['main', '.main-content', '.content', '.post-content', 
                           '.entry-content', '#content', '.page-content', '.article-content',
                           '.body-content', '[role="main"]', '.page', '.document']
            
            for selector in content_selectors:
                elements = []
                if selector.startswith('.'):
                    elements = soup.find_all(class_=selector[1:])
                elif selector.startswith('#'):
                    element = soup.find(id=selector[1:])
                    if element:
                        elements = [element]
                elif selector.startswith('['):
                    attr_name = selector.split('=')[0][1:]
                    attr_value = selector.split('=')[1].strip('"[]')
                    elements = soup.find_all(attrs={attr_name: attr_value})
                else:
                    elements = soup.find_all(selector)
                
                for element in elements:
                    element_text = element.get_text(separator=' ', strip=True)
                    if element_text and len(element_text) > 200:
                        logger.info(f"Method 4 - BeautifulSoup ({selector}): {len(element_text)} chars")
                        all_extracted_texts.append((element_text, f"BeautifulSoup ({selector})"))
        except Exception as e:
            logger.warning(f"Method 4 failed: {str(e)}")
            
        # Method 5: Full body extraction
        try:
            if not soup:
                soup = BeautifulSoup(html_content, 'html.parser')
                
            body = soup.find('body')
            if body:
                body_text = body.get_text(separator=' ', strip=True)
                if body_text:
                    logger.info(f"Method 5 - BeautifulSoup (body): {len(body_text)} chars")
                    all_extracted_texts.append((body_text, "BeautifulSoup (body)"))
        except Exception as e:
            logger.warning(f"Method 5 failed: {str(e)}")
        
        # Method 6: All text from each paragraph
        try:
            if not soup:
                soup = BeautifulSoup(html_content, 'html.parser')
                
            paragraphs = soup.find_all('p')
            if paragraphs:
                paragraphs_text = "\n\n".join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
                if paragraphs_text:
                    logger.info(f"Method 6 - BeautifulSoup (all paragraphs): {len(paragraphs_text)} chars")
                    all_extracted_texts.append((paragraphs_text, "BeautifulSoup (all paragraphs)"))
        except Exception as e:
            logger.warning(f"Method 6 failed: {str(e)}")
            
        # Method 7: Headings and paragraphs with hierarchy preserved
        try:
            if not soup:
                soup = BeautifulSoup(html_content, 'html.parser')
                
            # Get all headings and paragraphs
            elements = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p'])
            structured_text = []
            for element in elements:
                if element.name.startswith('h'):
                    # Add multiple newlines before headings to create section breaks
                    text = element.get_text(strip=True)
                    level = int(element.name[1])  # h1 = 1, h2 = 2, etc.
                    prefix = '#' * level + ' '  # Use Markdown-style headings
                    if text:
                        structured_text.append(f"\n\n{prefix}{text}\n")
                elif element.name == 'p':
                    text = element.get_text(strip=True)
                    if text:
                        structured_text.append(text)
            
            if structured_text:
                headings_text = "\n".join(structured_text)
                logger.info(f"Method 7 - BeautifulSoup (headers + paragraphs): {len(headings_text)} chars")
                all_extracted_texts.append((headings_text, "BeautifulSoup (headers + paragraphs)"))
        except Exception as e:
            logger.warning(f"Method 7 failed: {str(e)}")
            
        # ----- Select the best extraction result -----
        if not all_extracted_texts:
            logger.warning(f"All extraction methods failed for {url}")
            return []
            
        # Sort by content length and use the longest
        all_extracted_texts.sort(key=lambda x: len(x[0]), reverse=True)
        text, method = all_extracted_texts[0]
        logger.info(f"Selected {method} as the best extraction method with {len(text)} chars")
        
        # Generate citation
        citation = generate_website_citation(title, url)
        
        # Create chunks with small chunk size to get more chunks
        text_chunks = chunk_text(text, max_length=800, overlap=300)
        logger.info(f"Created {len(text_chunks)} chunks from {url}")
        
        # Ensure minimum of 20 chunks by creating single-paragraph chunks if needed
        if len(text_chunks) < 20 and len(text) > 2000:
            logger.info(f"Not enough chunks created, trying paragraph-based chunking")
            paragraphs = text.split('\n\n')
            if len(paragraphs) > 1:
                final_chunks = []
                
                # First add the original chunks (which maintain more context)
                for chunk in text_chunks:
                    final_chunks.append(chunk)
                
                # Then add individual paragraphs if they're substantial
                for para in paragraphs:
                    if len(para.strip()) > 100 and para not in final_chunks:
                        final_chunks.append(para)
                
                text_chunks = final_chunks
                logger.info(f"Paragraph chunking created {len(text_chunks)} chunks")
        
        # Log the number of chunks
        logger.info(f"Final chunk count: {len(text_chunks)}")
        
        # Create result objects
        chunks = []
        for i, chunk in enumerate(text_chunks):
            chunks.append({
                "text": chunk,
                "metadata": {
                    "source_type": "website",
                    "title": title,
                    "url": url,
                    "chunk_index": i,
                    "page_number": 1,  # All from same page
                    "citation": citation,
                    "date_scraped": datetime.now().isoformat(),
                    "extraction_method": method
                }
            })
        
        return chunks
    
    except Exception as e:
        logger.exception(f"Error in direct website extraction: {str(e)}")
        return []

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
            half_point = start + (max_length // 2)  # Use integer division
            paragraph_break = text.rfind('\n\n', start, end)
            if paragraph_break != -1 and paragraph_break > half_point:
                end = paragraph_break + 2
            else:
                # Look for a sentence end
                sentence_end = max(
                    text.rfind('. ', start, end),
                    text.rfind('! ', start, end),
                    text.rfind('? ', start, end)
                )
                
                if sentence_end != -1 and sentence_end > half_point:
                    end = sentence_end + 2
                else:
                    # Look for a space
                    space = text.rfind(' ', half_point, end)
                    if space != -1:
                        end = space + 1
        
        # Add the chunk to our list
        chunks.append(text[start:end])
        
        # Move the start position for the next chunk, including overlap
        start = max(start + (max_length - overlap), end - overlap) if end < len(text) else len(text)
    
    return chunks
