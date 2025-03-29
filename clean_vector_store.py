import os
import logging
import sys
import pickle
import hashlib
from collections import defaultdict

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])

logger = logging.getLogger(__name__)

def clean_vector_store():
    """
    This script cleans the vector store by:
    1. Removing duplicate documents (keeping only one representative per PDF)
    2. Ensuring all documents have proper metadata
    3. Fixing the overall structure to be more consistent
    """
    try:
        # Load the vector store data
        logger.info("Loading vector store data from document_data.pkl")
        
        # Create a backup before making changes
        backup_name = f"document_data.pkl.bak.cleanup.{int(os.path.getmtime('document_data.pkl'))}"
        logger.info(f"Creating backup at {backup_name}")
        with open("document_data.pkl", "rb") as f_src:
            with open(backup_name, "wb") as f_dst:
                f_dst.write(f_src.read())
        
        with open("document_data.pkl", "rb") as f:
            vector_store_data = pickle.load(f)
        
        # Get documents from vector store
        documents = vector_store_data.get("documents", {})
        logger.info(f"Vector store has {len(documents)} total documents")
        
        # Group documents by source/PDF
        docs_by_source = defaultdict(list)
        for doc_id, doc_data in documents.items():
            metadata = doc_data.get("metadata", {})
            if metadata.get("source_type") == "pdf":
                # Try to identify the source using various metadata fields
                source_id = None
                
                # Use db_id if available
                if metadata.get("db_id"):
                    source_id = f"db_{metadata.get('db_id')}"
                # Otherwise use DOI
                elif metadata.get("doi"):
                    source_id = f"doi_{metadata.get('doi')}"
                # Otherwise use filename
                elif metadata.get("filename"):
                    source_id = f"file_{metadata.get('filename')}"
                # Otherwise use file_path
                elif metadata.get("file_path"):
                    source_id = f"path_{metadata.get('file_path')}"
                # Otherwise fall back to hash of content
                else:
                    content_hash = hashlib.md5(doc_data.get("text", "").encode('utf-8')).hexdigest()
                    source_id = f"hash_{content_hash}"
                
                docs_by_source[source_id].append((doc_id, doc_data))
        
        logger.info(f"Found {len(docs_by_source)} unique source documents")
        
        # Count total duplicates
        total_docs = 0
        for source_id, docs in docs_by_source.items():
            total_docs += len(docs)
        
        # Create a new documents dictionary with deduplicated entries
        new_documents = {}
        
        # For each source, keep only one representative document
        for source_id, docs in docs_by_source.items():
            # Sort by most metadata fields (assuming more metadata = better quality)
            docs.sort(key=lambda x: len(x[1].get("metadata", {})), reverse=True)
            
            # Keep the one with the most metadata
            best_doc_id, best_doc = docs[0]
            new_documents[best_doc_id] = best_doc
            
            # Log if we removed duplicates
            if len(docs) > 1:
                logger.info(f"Kept 1 document out of {len(docs)} for source {source_id}")
        
        logger.info(f"Reduced from {total_docs} to {len(new_documents)} documents")
        
        # Update document counts
        document_counts = vector_store_data.get("document_counts", {})
        if "pdf" in document_counts:
            document_counts["pdf"] = len([d for d in new_documents.values() if d.get("metadata", {}).get("source_type") == "pdf"])
        
        # Replace documents in vector store
        vector_store_data["documents"] = new_documents
        
        # Save the updated vector store
        logger.info("Saving updated vector store")
        with open("document_data.pkl", "wb") as f:
            pickle.dump(vector_store_data, f)
        
        logger.info("Vector store cleaned successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Error cleaning vector store: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    clean_vector_store()