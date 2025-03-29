import os
import logging
import sys
import pickle

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])

logger = logging.getLogger(__name__)

def dump_vector_structure():
    """
    Dump the structure of the vector store to understand its shape.
    """
    try:
        # Load the vector store data
        logger.info("Loading vector store data from document_data.pkl")
        with open("document_data.pkl", "rb") as f:
            vector_store_data = pickle.load(f)
        
        # Print the top-level keys
        logger.info(f"Top-level keys: {list(vector_store_data.keys())}")
        
        # Documents
        documents = vector_store_data.get("documents", {})
        logger.info(f"Documents: {len(documents)}")
        
        # Look at a sample document
        if documents:
            sample_id = next(iter(documents))
            sample_doc = documents[sample_id]
            logger.info(f"Sample document structure for ID {sample_id}:")
            logger.info(f"  Keys: {list(sample_doc.keys())}")
            
            if "metadata" in sample_doc:
                logger.info(f"  Metadata keys: {list(sample_doc['metadata'].keys())}")
        
        # Chunks
        chunks = vector_store_data.get("chunks", {})
        logger.info(f"Chunks: {len(chunks)}")
        
        # Look at a sample chunk
        if chunks:
            sample_chunk_id = next(iter(chunks))
            sample_chunk = chunks[sample_chunk_id]
            logger.info(f"Sample chunk structure for ID {sample_chunk_id}:")
            logger.info(f"  Keys: {list(sample_chunk.keys())}")
            
            if "metadata" in sample_chunk:
                logger.info(f"  Metadata keys: {list(sample_chunk['metadata'].keys())}")
        
        # Doc chunks
        doc_chunks = vector_store_data.get("doc_chunks", {})
        logger.info(f"Doc chunks: {len(doc_chunks)}")
        
        if doc_chunks:
            sample_doc_id = next(iter(doc_chunks))
            sample_doc_chunks = doc_chunks[sample_doc_id]
            logger.info(f"Sample doc_chunks for doc ID {sample_doc_id}: {len(sample_doc_chunks)} chunks")
        
        # Embeddings
        embeddings = vector_store_data.get("embeddings", {})
        logger.info(f"Embeddings: {len(embeddings)}")
        
        # Index
        index = vector_store_data.get("index")
        if index:
            logger.info(f"Index is present")
        else:
            logger.info(f"No index found")
            
        return True
        
    except Exception as e:
        logger.error(f"Error dumping vector structure: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    dump_vector_structure()