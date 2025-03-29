"""
Utility functions for looking up DOI information from external APIs and
extracting DOIs from document text.

This can be used to enhance citation information when a DOI is available
but other metadata is missing.
"""

import re

import logging
import requests
import time
from typing import Dict, Optional, Any, Tuple

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def lookup_doi_metadata(doi: str) -> Optional[Dict[str, Any]]:
    """
    Look up metadata for a DOI using the Crossref API.
    
    Args:
        doi (str): The DOI to look up.
        
    Returns:
        Optional[Dict[str, Any]]: The metadata for the DOI, or None if not found.
    """
    if not doi:
        logger.warning("No DOI provided for lookup")
        return None
    
    # Clean the DOI
    doi = doi.strip().lower()
    if doi.startswith("https://doi.org/"):
        doi = doi[16:]
    elif doi.startswith("doi:"):
        doi = doi[4:]
    
    # First try CrossRef API (more reliable and no rate limits for basic usage)
    crossref_url = f"https://api.crossref.org/works/{doi}"
    
    try:
        # Add email for polite API usage
        headers = {
            "User-Agent": "ROXI/1.0 (Rheumatology Optimized eXpert Intelligence; mailto:none@example.com)"
        }
        
        logger.debug(f"Looking up DOI {doi} from CrossRef")
        response = requests.get(crossref_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if "message" in data:
                metadata = extract_crossref_metadata(data["message"])
                logger.debug(f"Found metadata for DOI {doi} from CrossRef: {metadata}")
                return metadata
        else:
            logger.warning(f"CrossRef API returned status code {response.status_code} for DOI {doi}")
    
    except Exception as e:
        logger.exception(f"Error looking up DOI {doi} from CrossRef: {str(e)}")
    
    # Fallback to DataCite API
    datacite_url = f"https://api.datacite.org/dois/{doi}"
    
    try:
        logger.debug(f"Looking up DOI {doi} from DataCite (fallback)")
        response = requests.get(datacite_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if "data" in data and "attributes" in data["data"]:
                metadata = extract_datacite_metadata(data["data"]["attributes"])
                logger.debug(f"Found metadata for DOI {doi} from DataCite: {metadata}")
                return metadata
        else:
            logger.warning(f"DataCite API returned status code {response.status_code} for DOI {doi}")
    
    except Exception as e:
        logger.exception(f"Error looking up DOI {doi} from DataCite: {str(e)}")
    
    # If both APIs fail, return None
    logger.warning(f"Could not find metadata for DOI {doi} from any source")
    return None

def extract_crossref_metadata(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract relevant metadata from CrossRef API response.
    
    Args:
        data (Dict[str, Any]): The CrossRef API response data.
        
    Returns:
        Dict[str, Any]: The extracted metadata.
    """
    metadata = {}
    
    # Extract basic metadata
    if "title" in data and data["title"]:
        metadata["title"] = data["title"][0]
    
    if "container-title" in data and data["container-title"]:
        metadata["journal"] = data["container-title"][0]
    
    # Extract authors
    if "author" in data and data["author"]:
        authors = []
        for author in data["author"]:
            if "family" in author and "given" in author:
                authors.append(f"{author['family']}, {author['given']}")
            elif "family" in author:
                authors.append(author["family"])
        metadata["authors"] = ", ".join(authors)
    
    # Extract publication date
    if "published-print" in data and "date-parts" in data["published-print"]:
        date_parts = data["published-print"]["date-parts"][0]
        if len(date_parts) >= 1:
            metadata["publication_year"] = date_parts[0]
    elif "published-online" in data and "date-parts" in data["published-online"]:
        date_parts = data["published-online"]["date-parts"][0]
        if len(date_parts) >= 1:
            metadata["publication_year"] = date_parts[0]
    elif "created" in data and "date-parts" in data["created"]:
        date_parts = data["created"]["date-parts"][0]
        if len(date_parts) >= 1:
            metadata["publication_year"] = date_parts[0]
    
    # Extract volume and issue
    if "volume" in data:
        metadata["volume"] = data["volume"]
    if "issue" in data:
        metadata["issue"] = data["issue"]
    
    # Extract page numbers
    if "page" in data:
        metadata["pages"] = data["page"]
    
    # Format citation
    metadata["formatted_citation"] = format_citation(metadata)
    
    return metadata

def extract_datacite_metadata(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract relevant metadata from DataCite API response.
    
    Args:
        data (Dict[str, Any]): The DataCite API response data.
        
    Returns:
        Dict[str, Any]: The extracted metadata.
    """
    metadata = {}
    
    # Extract basic metadata
    if "titles" in data and data["titles"]:
        for title_obj in data["titles"]:
            if "title" in title_obj:
                metadata["title"] = title_obj["title"]
                break
    
    if "container" in data and data["container"]:
        metadata["journal"] = data["container"]["title"]
    
    # Extract authors
    if "creators" in data and data["creators"]:
        authors = []
        for creator in data["creators"]:
            if "name" in creator:
                authors.append(creator["name"])
        metadata["authors"] = ", ".join(authors)
    
    # Extract publication date
    if "publicationYear" in data:
        metadata["publication_year"] = data["publicationYear"]
    elif "dates" in data and data["dates"]:
        for date_obj in data["dates"]:
            if "date" in date_obj and date_obj.get("dateType") == "Issued":
                try:
                    year = int(date_obj["date"][:4])
                    metadata["publication_year"] = year
                except (ValueError, TypeError):
                    pass
                break
    
    # Format citation
    metadata["formatted_citation"] = format_citation(metadata)
    
    return metadata

def format_citation(metadata: Dict[str, Any]) -> str:
    """
    Format a citation string from metadata.
    
    Args:
        metadata (Dict[str, Any]): The metadata to format.
        
    Returns:
        str: The formatted citation.
    """
    parts = []
    
    # Authors
    if "authors" in metadata and metadata["authors"]:
        parts.append(metadata["authors"])
    
    # Title
    if "title" in metadata and metadata["title"]:
        parts.append(metadata["title"])
    
    # Journal
    if "journal" in metadata and metadata["journal"]:
        journal_parts = [metadata["journal"]]
        
        # Year
        if "publication_year" in metadata and metadata["publication_year"]:
            journal_parts.append(f"({metadata['publication_year']})")
        
        # Volume
        if "volume" in metadata and metadata["volume"]:
            vol_parts = [metadata["volume"]]
            
            # Issue
            if "issue" in metadata and metadata["issue"]:
                vol_parts.append(f"({metadata['issue']})")
            
            journal_parts.append("".join(vol_parts))
        
        # Pages
        if "pages" in metadata and metadata["pages"]:
            journal_parts.append(f":{metadata['pages']}")
        
        parts.append(" ".join(journal_parts))
    elif "publication_year" in metadata and metadata["publication_year"]:
        # If no journal but there's a year
        parts.append(f"({metadata['publication_year']})")
    
    # Join all parts
    citation = ". ".join(parts)
    
    # Add DOI if we have one and it's not already in the citation
    if "doi" in metadata and metadata["doi"] and "doi" not in citation.lower():
        citation += f". https://doi.org/{metadata['doi']}"
    
    return citation

def extract_doi_from_text(text: str) -> Optional[str]:
    """
    Extract DOI from text using regex pattern matching.
    Enhanced version that handles more cases and is more aggressive in finding DOIs.
    
    Args:
        text (str): The text to search for DOIs.
        
    Returns:
        Optional[str]: The first DOI found, or None if no DOI is found.
    """
    if not text:
        return None
    
    # Common DOI patterns:
    # 1. Full URL: https://doi.org/10.xxxx/yyyy
    # 2. Prefixed: doi:10.xxxx/yyyy
    # 3. Plain: 10.xxxx/yyyy
    # 4. DOI in parentheses: (doi: 10.xxxx/yyyy) or (10.xxxx/yyyy)
    # 5. DOI with text: DOI 10.xxxx/yyyy or Digital Object Identifier: 10.xxxx/yyyy
    
    # Regex pattern to match DOIs - ordered by specificity
    doi_patterns = [
        # URL formats
        r'https?://doi\.org/10\.\d+/[^\s"\'<>)]+',  # URL format
        
        # Explicit DOI labels
        r'(?:doi|DOI)[\s:=]+10\.\d+/[^\s"\'<>)]+',  # doi: prefix or DOI: prefix
        r'(?:Digital Object Identifier|D\.O\.I\.)[\s:=]+10\.\d+/[^\s"\'<>)]+',  # Full label
        
        # Parenthesized formats
        r'\(doi[\s:]*10\.\d+/[^\s"\'<>)]+\)',  # (doi: 10.xxxx/yyyy)
        r'\(10\.\d+/[^\s"\'<>)]+\)',  # (10.xxxx/yyyy)
        
        # Plain DOI format - most generic, should be last
        r'10\.\d+/[^\s"\'<>)]+'  # plain format
    ]
    
    # First try patterns in order (most specific first)
    for pattern in doi_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            found_doi = match.group(0)
            # Clean up the DOI
            found_doi = clean_doi(found_doi)
            logger.debug(f"Extracted DOI from text (first pass): {found_doi}")
            return found_doi
    
    # If that didn't work, try a more aggressive search by looking for "10." followed by digits and slash
    # This is more prone to false positives but helps with difficult cases
    # Look near typical DOI markers
    doi_markers = [
        "doi", "DOI", "https://doi", "object identifier", 
        "citation", "reference", "article", "journal"
    ]
    
    # For each marker, look nearby (within 100 chars) for a potential DOI
    for marker in doi_markers:
        marker_pos = text.lower().find(marker)
        if marker_pos >= 0:
            # Get surrounding text (50 chars before, 100 chars after marker)
            start = max(0, marker_pos - 50)
            end = min(len(text), marker_pos + 100)
            context = text[start:end]
            
            # Look for "10." followed by digits and slash in this context
            match = re.search(r'10\.\d+/[^\s"\'<>)]+', context)
            if match:
                found_doi = match.group(0)
                found_doi = clean_doi(found_doi)
                logger.debug(f"Extracted DOI from text near '{marker}': {found_doi}")
                return found_doi
    
    # Final attempt: check if there's a PubMed or PMC ID, which we could potentially use for lookup
    # (not implemented yet, just flagging the possibility)
    pubmed_match = re.search(r'(?:PMID|pubmed)[\s:]*(\d+)', text, re.IGNORECASE)
    if pubmed_match:
        logger.debug(f"Found PubMed ID but no DOI: {pubmed_match.group(1)}")
        # In the future, we could implement PubMed ID to DOI conversion
    
    return None

def clean_doi(doi_text: str) -> str:
    """
    Clean a DOI string by removing prefixes and extra characters.
    
    Args:
        doi_text (str): The DOI string to clean.
        
    Returns:
        str: The cleaned DOI.
    """
    # Remove common prefixes
    prefixes = [
        'https://doi.org/', 'http://doi.org/', 
        'doi:', 'DOI:', 'doi ', 'DOI ', 
        'Digital Object Identifier:', 'D.O.I.:',
        'Digital Object Identifier ', 'D.O.I. '
    ]
    
    result = doi_text.strip()
    
    # Handle parenthesized DOIs
    if result.startswith('(') and result.endswith(')'):
        result = result[1:-1].strip()
    
    # Remove prefixes
    for prefix in prefixes:
        if result.lower().startswith(prefix.lower()):
            result = result[len(prefix):].strip()
            break
    
    # Remove any trailing punctuation or problematic characters
    result = re.sub(r'[,.;:"\'<>)\s]+$', '', result)
    
    # Ensure it starts with 10.
    if not result.startswith('10.'):
        # Try to find 10. in the string
        match = re.search(r'10\.\d+/[^\s"\'<>)]+', result)
        if match:
            result = match.group(0)
    
    return result

def get_citation_from_doi(doi: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Get citation information from a DOI.
    
    Args:
        doi (str): The DOI to look up.
        
    Returns:
        Tuple[bool, Dict[str, Any]]: A tuple containing:
            - bool: True if the lookup was successful, False otherwise.
            - Dict[str, Any]: The citation information, or an empty dict if not found.
    """
    if not doi:
        return False, {}
    
    metadata = lookup_doi_metadata(doi)
    
    if not metadata:
        return False, {}
    
    # Add the DOI to the metadata if it's not already there
    if "doi" not in metadata:
        metadata["doi"] = doi
    
    return True, metadata

def extract_and_get_citation(text: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Extract DOI from text and then get citation information.
    
    Args:
        text (str): The text to search for DOIs.
        
    Returns:
        Tuple[bool, Dict[str, Any]]: A tuple containing:
            - bool: True if the extraction and lookup were successful, False otherwise.
            - Dict[str, Any]: The citation information, or an empty dict if not found.
    """
    doi = extract_doi_from_text(text)
    if not doi:
        return False, {}
    
    return get_citation_from_doi(doi)

def get_metadata_from_doi(doi: str) -> Optional[Dict[str, Any]]:
    """
    Get metadata for a DOI. This is a convenience function for 
    lookup_doi_metadata that can be called from other modules.
    
    Args:
        doi (str): The DOI to look up.
        
    Returns:
        Optional[Dict[str, Any]]: The metadata for the DOI, or None if not found.
    """
    return lookup_doi_metadata(doi)