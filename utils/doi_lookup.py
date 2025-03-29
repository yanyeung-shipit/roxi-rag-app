"""
Utility functions for looking up DOI information from external APIs.
This can be used to enhance citation information when a DOI is available
but other metadata is missing.
"""

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