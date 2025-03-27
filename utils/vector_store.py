import os
import logging
import numpy as np
import faiss
import pickle
import uuid
from collections import defaultdict

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class VectorStore:
    def __init__(self, dimension=1536, index_path=None, data_path=None):
        """
        Initialize a vector store for document retrieval.
        
        Args:
            dimension (int): Dimension of the vectors
            index_path (str): Path to load existing Faiss index
            data_path (str): Path to load existing document data
        """
        # Default OpenAI embedding dimension is 1536
        self.dimension = dimension
        
        # Initialize FAISS index
        self.index = faiss.IndexFlatL2(dimension)
        
        # Dictionary to store document data
        self.documents = {}
        
        # Dictionary to store document counts by type
        self.document_counts = defaultdict(int)
        
        # Path for persistence
        self.index_path = index_path or "faiss_index.bin"
        self.data_path = data_path or "document_data.pkl"
        
        # Load existing data if available
        self._load_if_exists()
        
        logger.debug(f"Initialized vector store with dimension {dimension}")
    
    def _load_if_exists(self):
        """Load existing index and data if available."""
        try:
            if os.path.exists(self.index_path) and os.path.exists(self.data_path):
                logger.info("Loading existing vector store from disk")
                self.index = faiss.read_index(self.index_path)
                with open(self.data_path, 'rb') as f:
                    loaded_data = pickle.load(f)
                    self.documents = loaded_data.get('documents', {})
                    self.document_counts = loaded_data.get('document_counts', defaultdict(int))
                logger.info(f"Loaded {len(self.documents)} documents from disk")
        except Exception as e:
            logger.exception(f"Error loading vector store: {str(e)}")
    
    def _save(self):
        """Save the current index and data to disk."""
        try:
            faiss.write_index(self.index, self.index_path)
            with open(self.data_path, 'wb') as f:
                pickle.dump({
                    'documents': self.documents,
                    'document_counts': self.document_counts
                }, f)
            logger.debug("Vector store saved to disk")
        except Exception as e:
            logger.exception(f"Error saving vector store: {str(e)}")
    
    def add_text(self, text, metadata=None):
        """
        Add text to the vector store.
        
        Args:
            text (str): Text content to add
            metadata (dict): Metadata associated with the text
        """
        try:
            # Generate embedding for the text
            embedding = self._get_embedding(text)
            
            # Generate a unique ID for this document
            doc_id = str(uuid.uuid4())
            
            # Add to FAISS index
            self.index.add(np.array([embedding], dtype=np.float32))
            
            # Store document data
            self.documents[doc_id] = {
                'text': text,
                'metadata': metadata or {}
            }
            
            # Update document counts
            source_type = metadata.get('source_type', 'unknown') if metadata else 'unknown'
            self.document_counts[source_type] += 1
            
            # Save updated index and data
            self._save()
            
            logger.debug(f"Added document {doc_id} to vector store")
            return doc_id
        except Exception as e:
            logger.exception(f"Error adding text to vector store: {str(e)}")
            raise
    
    def search(self, query, top_k=5):
        """
        Search for documents similar to the query.
        
        Args:
            query (str): Query text
            top_k (int): Number of results to return
            
        Returns:
            list: List of documents with similarity scores
        """
        try:
            if len(self.documents) == 0:
                logger.warning("Search performed on empty vector store")
                return []
            
            # Generate embedding for the query
            query_embedding = self._get_embedding(query)
            
            # Perform search
            k = min(top_k, len(self.documents))
            distances, indices = self.index.search(
                np.array([query_embedding], dtype=np.float32), k
            )
            
            # Format results
            results = []
            for i, idx in enumerate(indices[0]):
                if idx < 0 or idx >= len(self.documents):
                    continue
                
                # Get document by index
                doc_id = list(self.documents.keys())[idx]
                doc = self.documents[doc_id]
                
                results.append({
                    'id': doc_id,
                    'text': doc['text'],
                    'metadata': doc['metadata'],
                    'score': float(distances[0][i])
                })
            
            logger.debug(f"Search returned {len(results)} results")
            return results
        except Exception as e:
            logger.exception(f"Error searching vector store: {str(e)}")
            raise
    
    def get_stats(self):
        """
        Get statistics about the vector store.
        
        Returns:
            dict: Statistics about the vector store
        """
        return {
            'total_documents': len(self.documents),
            'chunks': len(self.documents),
            'websites': self.document_counts.get('website', 0),
            'pdfs': self.document_counts.get('pdf', 0)
        }
    
    def clear(self):
        """Clear all documents from the vector store."""
        try:
            self.index = faiss.IndexFlatL2(self.dimension)
            self.documents = {}
            self.document_counts = defaultdict(int)
            self._save()
            logger.debug("Vector store cleared")
        except Exception as e:
            logger.exception(f"Error clearing vector store: {str(e)}")
            raise
    
    def _get_embedding(self, text):
        """
        Get embedding for text.
        
        Args:
            text (str): Text to embed
            
        Returns:
            numpy.ndarray: Embedding vector
        """
        # This is a placeholder. In a real implementation, you would use
        # a proper embedding model (OpenAI, Hugging Face, etc.)
        # For now, we'll use a random vector for demonstration
        # In production, replace this with actual embeddings
        
        try:
            from utils.llm_service import get_embedding
            return get_embedding(text)
        except:
            # Fallback to random embedding for testing
            logger.warning("Using random embedding (for testing only)")
            return np.random.rand(self.dimension).astype(np.float32)
