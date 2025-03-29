import re
import os
import json
import logging
import requests
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import fitz  # PyMuPDF

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Regular expressions for DOI detection
DOI_PATTERNS = [
    # Standard DOI pattern (most common)
    r'\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)\b',
    # DOI with "doi:" prefix
    r'doi:?\s*(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)',
    # DOI with "DOI:" prefix
    r'DOI:?\s*(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)',
    # DOI with "https://doi.org/" prefix
    r'https?://doi\.org/(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)',
]

def extract_doi_from_text(text: str) -> Optional[str]:
    """
    Extract DOI from text using regular expressions.
    
    Args:
        text (str): Text to search for DOI
        
    Returns:
        Optional[str]: Extracted DOI or None if not found
    """
    if not text:
        return None
        
    for pattern in DOI_PATTERNS:
        matches = re.findall(pattern, text)
        if matches:
            # Return the first match, cleaned up
            doi = matches[0]
            # If the pattern captured a group, it might return a tuple
            if isinstance(doi, tuple):
                doi = doi[0]
            return doi.strip()
    
    return None

def extract_doi_from_pdf(pdf_path: str) -> Optional[str]:
    """
    Extract DOI from a PDF file by examining the first few pages.
    
    Args:
        pdf_path (str): Path to the PDF file
        
    Returns:
        Optional[str]: Extracted DOI or None if not found
    """
    try:
        logger.debug(f"Extracting DOI from PDF: {pdf_path}")
        # Open the PDF
        doc = fitz.open(pdf_path)
        
        # Try to extract DOI from document metadata first
        metadata = doc.metadata
        if metadata:
            # Check if DOI is in the metadata
            for key in ['doi', 'DOI', 'Subject', 'Keywords']:
                if key in metadata and metadata[key]:
                    doi = extract_doi_from_text(metadata[key])
                    if doi:
                        logger.debug(f"Found DOI in metadata: {doi}")
                        return doi
        
        # If DOI wasn't in metadata, search in the text of the first few pages
        # Focus on first page, header/footer areas, and the references section
        pages_to_check = min(5, len(doc))
        
        for page_num in range(pages_to_check):
            page = doc[page_num]
            
            # Extract text from the page
            text = page.get_text()
            
            # Check if this could be a references page
            is_references_page = any(ref in text.lower() for ref in ["references", "bibliography", "cited works"])
            
            # For the first page and references pages, check more thoroughly
            if page_num == 0 or is_references_page:
                doi = extract_doi_from_text(text)
                if doi:
                    logger.debug(f"Found DOI on page {page_num+1}: {doi}")
                    return doi
            
            # For other pages, just check headers and footers
            # (approximately top and bottom 20% of the page)
            else:
                # Get page dimensions
                page_rect = page.rect
                height = page_rect.height
                
                # Extract header text (top 20% of the page)
                header_rect = fitz.Rect(0, 0, page_rect.width, height * 0.2)
                header_text = page.get_text("text", clip=header_rect)
                
                # Extract footer text (bottom 20% of the page)
                footer_rect = fitz.Rect(0, height * 0.8, page_rect.width, height)
                footer_text = page.get_text("text", clip=footer_rect)
                
                # Check header and footer for DOI
                doi = extract_doi_from_text(header_text) or extract_doi_from_text(footer_text)
                if doi:
                    logger.debug(f"Found DOI in header/footer of page {page_num+1}: {doi}")
                    return doi
        
        logger.debug("No DOI found in PDF")
        return None
        
    except Exception as e:
        logger.error(f"Error extracting DOI from PDF: {str(e)}")
        return None
    
def fetch_metadata_from_crossref(doi: str) -> Optional[Dict[str, Any]]:
    """
    Fetch metadata for a DOI from the CrossRef API.
    
    Args:
        doi (str): DOI to look up
        
    Returns:
        Optional[Dict[str, Any]]: Metadata dictionary or None if not found
    """
    try:
        # CrossRef API endpoint
        url = f"https://api.crossref.org/works/{doi}"
        
        # Add a proper user agent (CrossRef recommends this)
        headers = {
            'User-Agent': 'ROXI/1.0 (Rheumatology Optimized eXpert Intelligence; mailto:user@example.com)',
            'Accept': 'application/json'
        }
        
        # Make the request
        response = requests.get(url, headers=headers, timeout=10)
        
        # Check if the request was successful
        if response.status_code == 200:
            data = response.json()
            if 'message' in data:
                logger.debug(f"Successfully retrieved metadata for DOI: {doi}")
                return data['message']
            
        logger.warning(f"Failed to retrieve metadata for DOI ({doi}): HTTP {response.status_code}")
        return None
        
    except Exception as e:
        logger.error(f"Error fetching metadata from CrossRef: {str(e)}")
        return None

def fetch_metadata_from_pubmed(doi: str) -> Optional[Dict[str, Any]]:
    """
    Fetch metadata for a DOI from the PubMed API.
    Used as a fallback when CrossRef fails.
    
    Args:
        doi (str): DOI to look up
        
    Returns:
        Optional[Dict[str, Any]]: Metadata dictionary or None if not found
    """
    try:
        # First, search for the article by DOI
        search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={doi}[DOI]&retmode=json"
        search_response = requests.get(search_url, timeout=10)
        
        if search_response.status_code != 200:
            logger.warning(f"PubMed search failed: HTTP {search_response.status_code}")
            return None
        
        search_data = search_response.json()
        id_list = search_data.get('esearchresult', {}).get('idlist', [])
        
        if not id_list:
            logger.warning(f"No PubMed records found for DOI: {doi}")
            return None
        
        # Get the first PubMed ID
        pmid = id_list[0]
        
        # Now fetch the full record
        fetch_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={pmid}&retmode=json"
        fetch_response = requests.get(fetch_url, timeout=10)
        
        if fetch_response.status_code != 200:
            logger.warning(f"PubMed fetch failed: HTTP {fetch_response.status_code}")
            return None
        
        fetch_data = fetch_response.json()
        result = fetch_data.get('result', {}).get(pmid, {})
        
        if result:
            logger.debug(f"Successfully retrieved PubMed metadata for DOI: {doi}")
            return {
                'title': result.get('title', ''),
                'authors': [{'family': author.get('name', '').split()[-1], 
                             'given': ' '.join(author.get('name', '').split()[:-1])} 
                            for author in result.get('authors', [])],
                'container-title': result.get('fulljournalname', ''),
                'volume': result.get('volume', ''),
                'issue': result.get('issue', ''),
                'page': result.get('pages', ''),
                'published': {'date-parts': [[int(result.get('pubdate', '').split()[0])]]},
                'DOI': doi
            }
        
        logger.warning(f"No usable data found in PubMed response for DOI: {doi}")
        return None
        
    except Exception as e:
        logger.error(f"Error fetching metadata from PubMed: {str(e)}")
        return None

def format_citation_apa(metadata: Dict[str, Any]) -> str:
    """
    Format metadata as an APA 7th edition citation string.
    
    Args:
        metadata (Dict[str, Any]): Metadata dictionary (from CrossRef or PubMed)
        
    Returns:
        str: Formatted citation string
    """
    try:
        # Extract authors
        authors_list = []
        if 'author' in metadata:
            for author in metadata['author'][:6]:  # APA truncates after 6 authors
                family = author.get('family', '')
                given = author.get('given', '')
                
                if family and given:
                    # Format as "Family, G."
                    initials = ''.join([f"{name[0]}." for name in given.split()])
                    authors_list.append(f"{family}, {initials}")
                elif family:  # Handle cases with only family name
                    authors_list.append(family)
        
        # Handle case with more than 6 authors
        if 'author' in metadata and len(metadata['author']) > 6:
            authors_list.append("et al.")
        
        # Join authors with commas and ampersand
        if authors_list:
            if len(authors_list) == 1:
                authors_text = authors_list[0]
            else:
                authors_text = ", ".join(authors_list[:-1]) + ", & " + authors_list[-1]
        else:
            authors_text = ""
        
        # Extract title
        title = metadata.get('title', [""])[0] if isinstance(metadata.get('title', []), list) else metadata.get('title', "")
        
        # Extract journal/container title
        journal = metadata.get('container-title', [""])[0] if isinstance(metadata.get('container-title', []), list) else metadata.get('container-title', "")
        
        # Make journal title italic by surrounding with <em> tags (for HTML display)
        journal_formatted = f"<em>{journal}</em>" if journal else ""
        
        # Extract volume, issue, and page numbers
        volume = metadata.get('volume', "")
        issue = metadata.get('issue', "")
        page = metadata.get('page', "")
        
        # Format volume and issue
        volume_issue = f"{volume}"
        if issue:
            volume_issue += f"({issue})"
        
        # Extract year
        year = ""
        if 'published' in metadata and 'date-parts' in metadata['published']:
            date_parts = metadata['published']['date-parts']
            if date_parts and date_parts[0]:
                year = str(date_parts[0][0])
        elif 'published-print' in metadata and 'date-parts' in metadata['published-print']:
            date_parts = metadata['published-print']['date-parts']
            if date_parts and date_parts[0]:
                year = str(date_parts[0][0])
        
        # Extract DOI
        doi = metadata.get('DOI', "")
        
        # Build the citation string
        citation_parts = []
        
        # Authors and year
        if authors_text and year:
            citation_parts.append(f"{authors_text} ({year}).")
        elif authors_text:
            citation_parts.append(f"{authors_text} (n.d.).")
        elif year:
            citation_parts.append(f"({year}).")
        
        # Title
        if title:
            citation_parts.append(f" {title}.")
        
        # Journal, volume, issue, and pages
        journal_info = []
        if journal_formatted:
            journal_info.append(journal_formatted)
        if volume_issue:
            journal_info.append(volume_issue)
        if page:
            journal_info.append(page)
            
        if journal_info:
            citation_parts.append(f" {', '.join(journal_info)}.")
        
        # DOI
        if doi:
            citation_parts.append(f" https://doi.org/{doi}")
        
        # Combine all parts
        return "".join(citation_parts)
        
    except Exception as e:
        logger.error(f"Error formatting citation: {str(e)}")
        return "Citation information unavailable."

def extract_citation_info(filename: str, pdf_path: Optional[str] = None) -> Tuple[str, Optional[Dict]]:
    """
    Extract citation information from a PDF file, attempting multiple methods.
    
    Args:
        filename (str): Name of the file for fallback citation
        pdf_path (str, optional): Path to the PDF file
        
    Returns:
        Tuple[str, Optional[Dict]]: Formatted citation string and raw metadata
    """
    # Initialize response data
    citation = ""
    metadata = None
    
    # If we have a PDF file, try to extract DOI and citation info
    if pdf_path:
        try:
            # Extract DOI from PDF
            doi = extract_doi_from_pdf(pdf_path)
            
            if doi:
                logger.debug(f"Found DOI in PDF: {doi}")
                
                # Try CrossRef API first
                metadata = fetch_metadata_from_crossref(doi)
                
                # If CrossRef fails, try PubMed
                if not metadata:
                    logger.debug("CrossRef lookup failed, trying PubMed")
                    metadata = fetch_metadata_from_pubmed(doi)
                
                # If we got metadata, format the citation
                if metadata:
                    citation = format_citation_apa(metadata)
                    logger.debug(f"Generated citation: {citation}")
                    return citation, metadata
        
        except Exception as e:
            logger.error(f"Error during citation extraction: {str(e)}")
    
    # If we couldn't extract citation info, create a fallback citation from the filename
    # Do not import from document_processor to avoid circular reference
    
    # Remove file extension if present
    base_name = os.path.splitext(filename)[0].lower()
    
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
        citation = f"{author}, {author[0].upper()}. ({year}). {title}. Retrieved {formatted_date}."
        return citation, metadata
    
    # Try to handle filenames with underscores as title elements (e.g., "cancer_research_2020.pdf")
    match = re.match(r'(.+)_(\d{4})', base_name)
    if match:
        title = match.group(1).replace('_', ' ').title()
        year = match.group(2)
        
        # Format as APA citation with title and year
        citation = f"{title} ({year}). Retrieved {formatted_date}."
        return citation, metadata
    
    # Clean the filename to create a better title
    title = base_name.replace('_', ' ').replace('-', ' ').title()
    
    # Default APA format for document with unknown year and author
    citation = f"{title} (n.d.). Retrieved {formatted_date}."
    
    return citation, metadata

def bulk_process_citation_batch(pdf_paths: List[Tuple[str, str]], batch_size: int = 10) -> List[Tuple[str, Dict, str]]:
    """
    Process citations for a batch of PDFs in a memory-efficient way.
    
    Args:
        pdf_paths (List[Tuple[str, str]]): List of (filename, pdf_path) tuples
        batch_size (int): Number of PDFs to process in each batch
        
    Returns:
        List[Tuple[str, Dict, str]]: List of (filename, metadata, citation) tuples
    """
    results = []
    
    # Process in batches to avoid memory issues
    for i in range(0, len(pdf_paths), batch_size):
        batch = pdf_paths[i:i+batch_size]
        
        for filename, pdf_path in batch:
            logger.debug(f"Processing citation for {filename}")
            citation, metadata = extract_citation_info(filename, pdf_path)
            results.append((filename, metadata, citation))
    
    return results