import os
import logging
import sys
import pickle
import psycopg2
import psycopg2.extras

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])

logger = logging.getLogger(__name__)

def diagnose_citations():
    """
    Print diagnostic information about citations in the vector store.
    """
    try:
        # Load the vector store data
        logger.info("Loading vector store data from document_data.pkl")
        with open("document_data.pkl", "rb") as f:
            vector_store_data = pickle.load(f)
        
        # Get documents from vector store
        documents = vector_store_data.get("documents", {})
        logger.info(f"Vector store has {len(documents)} total documents")
        
        # Count documents with citation data
        pdf_docs_with_citation = 0
        pdf_docs_with_formatted_citation = 0
        pdf_docs_total = 0
        
        for doc_id, doc_data in documents.items():
            metadata = doc_data.get("metadata", {})
            if metadata.get("source_type") == "pdf":
                pdf_docs_total += 1
                
                if metadata.get("citation"):
                    pdf_docs_with_citation += 1
                    
                if metadata.get("formatted_citation"):
                    pdf_docs_with_formatted_citation += 1
        
        logger.info(f"Found {pdf_docs_total} PDF documents in vector store")
        logger.info(f"  {pdf_docs_with_citation} have 'citation' field")
        logger.info(f"  {pdf_docs_with_formatted_citation} have 'formatted_citation' field")
        
        # Check if any documents have both citation and formatted_citation
        docs_with_both = 0
        for doc_id, doc_data in documents.items():
            metadata = doc_data.get("metadata", {})
            if metadata.get("citation") and metadata.get("formatted_citation"):
                docs_with_both += 1
                if docs_with_both <= 3:  # Show examples for first 3
                    logger.info(f"Example document with both citation types:")
                    logger.info(f"  citation: {metadata.get('citation')}")
                    logger.info(f"  formatted_citation: {metadata.get('formatted_citation')}")
        
        logger.info(f"Found {docs_with_both} documents with both citation types")
        
        return True
        
    except Exception as e:
        logger.error(f"Error diagnosing citations: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    diagnose_citations()