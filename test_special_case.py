"""
Test script specifically focused on the edge case of matching "Agca-EULAR-update.pdf"
"""
import logging
import sys
from app import app, document_exists
from models import Document

def test_agca_eular_hyphen_case():
    """
    Test the specific edge case of hyphenated compound names like "Agca-EULAR-update.pdf"
    This is problematic because it doesn't match by substring or by direct identifier.
    
    This test runs multiple potentially challenging filename matches to ensure our
    duplicate detection logic works correctly.
    """
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)s - %(message)s",
        stream=sys.stdout
    )
    
    # Try to find matches for 'Agca-EULAR-update.pdf'
    with app.app_context():
        print("\nSpecial case test: Agca-EULAR-update.pdf")
        filename = "Agca-EULAR-update.pdf"
        
        # Step 1: Extract the base filename for comparison
        base_filename = filename.rsplit('.', 1)[0] if '.' in filename else filename
        print(f"Base filename: {base_filename}")
        
        # Step 2: Directly query the database to see what documents exist
        search_pattern = "%Agca%"
        existing_docs = Document.query.filter(Document.filename.like(search_pattern)).all()
        
        print(f"Found {len(existing_docs)} potential documents with 'Agca' in the name:")
        for doc in existing_docs:
            print(f"  - {doc.filename}")
        
        # Step 3: Run document_exists with extra logging
        result = document_exists(filename)
        print(f"Match result: {result}")
        expected = True
        print(f"Expected: {expected}")
        assert result == expected, f"Expected {expected}, got {result}"
        
        # Test several more challenging edge cases
        test_cases = [
            ("EULAR_CVS_update.pdf", True),
            ("Agca2016.pdf", True),
            ("Agca_2016.pdf", True)
        ]
        
        for test_file, expected_result in test_cases:
            print(f"\nSpecial case test: {test_file}")
            result = document_exists(test_file)
            print(f"Match result: {result}")
            print(f"Expected: {expected_result}")
            assert result == expected_result, f"Expected {expected_result}, got {result}"
            
        print("\nAll special case tests passed!")

if __name__ == "__main__":
    test_agca_eular_hyphen_case()