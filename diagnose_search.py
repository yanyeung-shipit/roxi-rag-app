import os
import logging
import sys
import pickle
import json
from utils.vector_store import VectorStore

# Configure logging - only show our logs, not the OpenAI API logs
logging.basicConfig(level=logging.INFO, 
                    format='%(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])

# Disable other loggers
logging.getLogger("openai").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)
logging.getLogger("utils.vector_store").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

def diagnose_search():
    """
    Diagnose what happens during a vector store search.
    """
    try:
        # Initialize vector store
        vector_store = VectorStore()
        
        # Perform a sample search
        query = "rheumatoid arthritis guidelines"
        logger.info(f"Running sample search for: {query}")
        
        results = vector_store.search(query, top_k=5)
        
        # Analyze the results
        logger.info(f"Found {len(results)} results")
        
        for i, result in enumerate(results):
            logger.info(f"Result {i+1}:")
            logger.info(f"  Source type: {result.get('metadata', {}).get('source_type', 'unknown')}")
            
            # For PDFs, check citation information
            if result.get('metadata', {}).get('source_type') == 'pdf':
                logger.info(f"  Title: {result.get('metadata', {}).get('title', 'unknown')}")
                logger.info(f"  Page: {result.get('metadata', {}).get('page', 'unknown')}")
                logger.info(f"  Citation: {result.get('metadata', {}).get('citation', 'None')}")
                logger.info(f"  Formatted Citation: {result.get('metadata', {}).get('formatted_citation', 'None')}")
                logger.info(f"  DOI: {result.get('metadata', {}).get('doi', 'None')}")
            
            # Only show first 100 chars of content
            content = result.get('text', '')
            logger.info(f"  Content: {content[:100]}..." if len(content) > 100 else content)
            
            # Log all metadata keys for debugging
            metadata = result.get('metadata', {})
            logger.info(f"  Available metadata keys: {', '.join(metadata.keys())}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error diagnosing search: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    diagnose_search()