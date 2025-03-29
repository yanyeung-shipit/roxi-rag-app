"""
Test script to verify the duplicate detection functionality.
"""
import sys
import logging

# Initialize logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import from app.py in global scope
import app
from models import Document, db

def test_document_exists(test_filename, expected_result=None):
    """
    Test the document_exists function with a specific filename.
    
    Args:
        test_filename (str): The filename to test
        expected_result (bool, optional): The expected result. If None, don't verify.
    """
    print(f"\nTesting with filename: '{test_filename}'")
    result = app.document_exists(test_filename)
    print(f"Result: {result}")
    
    if expected_result is not None:
        assert result == expected_result, f"Expected {expected_result}, got {result}"
        print(f"✓ Test passed: {result} matches expected {expected_result}")
    
    return result

def main():
    """Run tests to verify the duplicate detection logic."""
    # Basic tests - known filenames
    test_document_exists("Agca2016-_EULAR_CVS_update.pdf", True)
    test_document_exists("20250327145551_Agca2016-_EULAR_CVS_update.pdf", True)
    
    # Tests with variant names
    test_document_exists("modified_Agca2016-_EULAR_CVS_update.pdf", True)
    test_document_exists("Agca2016_EULAR_CVS_update.pdf", True)
    test_document_exists("TEST_Agca2016-_EULAR_CVS_update.pdf", True)
    
    # Tests with completely different filenames
    test_document_exists("completely_different_file.pdf", False)
    test_document_exists("smolen2018_-_nature_review_primer.pdf", False) # The file doesn't exist in our database
    
    # Additional tests with some variation
    # Enable extra logging and show full debug info for this special test
    print("\nTesting the special partial matching case: 'Agca-EULAR-update.pdf'")
    import logging
    from app import document_exists
    prev_level = logging.getLogger().level
    logging.getLogger().setLevel(logging.DEBUG)
    test_document_exists("Agca-EULAR-update.pdf", True) # This tests partial matching
    logging.getLogger().setLevel(prev_level)
    
    # Test more challenging partial matches
    print("\nTesting more challenging match: 'EULAR_CVS_update.pdf'")
    logging.getLogger().setLevel(logging.DEBUG)
    test_document_exists("EULAR_CVS_update.pdf", True)
    print("\nTesting more challenging match: 'Agca2016.pdf'")
    test_document_exists("Agca2016.pdf", True)
    print("\nTesting more challenging match: 'Agca_2016.pdf'")
    test_document_exists("Agca_2016.pdf", True)
    logging.getLogger().setLevel(prev_level)
    
    # Test false positives - these should NOT match
    test_document_exists("NotAgca2016-_EULAR_CVS_update.pdf", False)
    test_document_exists("20250327145551_AgcaSomethingElseEntirely.pdf", False)
    
    print("\nAll tests completed.")

if __name__ == "__main__":
    with app.app.app_context():
        main()