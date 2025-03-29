"""
Test script to verify that the DOI lookup functionality works correctly.
"""

import logging
from utils.doi_lookup import get_citation_from_doi

# Configure logging
logging.basicConfig(level=logging.DEBUG)

def test_doi_lookup(doi):
    """
    Test the DOI lookup functionality with a specific DOI.
    
    Args:
        doi (str): The DOI to look up.
    """
    print(f"\nLooking up DOI: {doi}")
    success, metadata = get_citation_from_doi(doi)
    
    if success:
        print("\nDOI Lookup Successful!")
        print(f"Title: {metadata.get('title', 'N/A')}")
        print(f"Authors: {metadata.get('authors', 'N/A')}")
        print(f"Journal: {metadata.get('journal', 'N/A')}")
        print(f"Year: {metadata.get('publication_year', 'N/A')}")
        print(f"Volume: {metadata.get('volume', 'N/A')}")
        print(f"Issue: {metadata.get('issue', 'N/A')}")
        print(f"Pages: {metadata.get('pages', 'N/A')}")
        print(f"Formatted Citation: {metadata.get('formatted_citation', 'N/A')}")
    else:
        print("\nDOI Lookup Failed!")
        print("No metadata found for this DOI.")

def main():
    """
    Main function that tests the DOI lookup with several test DOIs.
    """
    # Test with a known good DOI from Nature Reviews Rheumatology
    test_doi_lookup("10.1038/nrdp.2018.1")
    
    # Test with a DOI from ACR/Wiley (Arthritis & Rheumatology)
    test_doi_lookup("10.1002/art.41752")
    
    # Test with a DOI from Rheumatology (Oxford Academic)
    test_doi_lookup("10.1093/rheumatology/kez624")
    
    # Test with a DOI from Annals of the Rheumatic Diseases
    test_doi_lookup("10.1136/annrheumdis-2019-216655")
    
    # Test with a DOI from The Lancet
    test_doi_lookup("10.1016/S0140-6736(20)32279-0")

if __name__ == "__main__":
    main()