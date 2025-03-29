#!/usr/bin/env python3
"""
Test script to directly debug website extraction.
This will directly test our content extraction methods on a given URL.
"""

import sys
import logging
from utils.web_scraper import extract_website_direct, create_minimal_content_for_topic

# Set up logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_website_extraction(url):
    """Test direct website extraction on a given URL."""
    print(f"\n\n===== TESTING DIRECT EXTRACTION ON: {url} =====")
    
    # Try the direct extraction method
    print("\n1. Testing extract_website_direct:")
    results_direct = extract_website_direct(url)
    print(f"   - Extracted {len(results_direct)} chunks")
    if results_direct:
        print(f"   - First chunk: {results_direct[0]['text'][:100]}...")
        print(f"   - Extraction method: {results_direct[0]['metadata']['extraction_method']}")
    
    # Try the topic extraction method
    print("\n2. Testing create_minimal_content_for_topic:")
    results_topic = create_minimal_content_for_topic(url)
    print(f"   - Extracted {len(results_topic)} chunks")
    if results_topic:
        print(f"   - First chunk: {results_topic[0]['text'][:100]}...")
    
    print("\n===== COMPARISON =====")
    print(f"Direct extraction: {len(results_direct)} chunks")
    print(f"Topic extraction:  {len(results_topic)} chunks")
    
    # Show extraction stats
    if results_direct:
        print("\n===== EXTRACTION STATS FOR DIRECT METHOD =====")
        methods = {}
        for chunk in results_direct:
            method = chunk['metadata']['extraction_method']
            methods[method] = methods.get(method, 0) + 1
        
        for method, count in methods.items():
            print(f"   - {method}: {count} chunks")
    
    print("\n===== DETAILED CHUNK CONTENT SAMPLE =====")
    if results_direct and len(results_direct) > 0:
        # Print first 3 chunks
        for i, chunk in enumerate(results_direct[:3]):
            print(f"\nChunk {i+1}/{len(results_direct)}:")
            print("-" * 50)
            print(chunk['text'][:300] + "...")
            print("-" * 50)

def main():
    """Main function to run the script with command line arguments."""
    if len(sys.argv) < 2:
        print("Usage: python website_extraction_test.py <url>")
        print("Example: python website_extraction_test.py https://rheum.reviews/topic/rheumatoid-arthritis/")
        sys.exit(1)
    
    url = sys.argv[1]
    test_website_extraction(url)

if __name__ == "__main__":
    main()