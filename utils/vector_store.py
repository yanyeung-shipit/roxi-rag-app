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
            
        Returns:
            str: Document ID if successful
            
        Raises:
            Exception: If an error occurs
        """
        try:
            # Skip empty or very short text
            if not text or len(text) < 10:
                logger.warning("Skipped adding very short or empty text")
                return None
                
            # Limit text length to prevent issues with very large texts
            max_text_length = 10000
            if len(text) > max_text_length:
                logger.warning(f"Text truncated from {len(text)} to {max_text_length} characters")
                text = text[:max_text_length] + "..."
            
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
            
            # Save updated index and data - don't save every time to improve performance
            # Only save every 10 documents or if we have key metadata document types
            if len(self.documents) % 10 == 0 or source_type in ['website', 'pdf']:
                self._save()
                logger.debug("Vector store saved to disk")
            
            logger.debug(f"Added document {doc_id} to vector store")
            return doc_id
        except Exception as e:
            logger.exception(f"Error adding text to vector store: {str(e)}")
            # If the error is related to embedding, we can try to continue with a simplified version
            try:
                if "embed" in str(e).lower():
                    logger.warning("Attempting to clean and retry adding text")
                    # Clean and simplify text
                    clean_text = ' '.join(text.split())[:5000]  # Simplify and limit length
                    
                    # Try again with cleaned text
                    embedding = self._get_embedding(clean_text)
                    doc_id = str(uuid.uuid4())
                    self.index.add(np.array([embedding], dtype=np.float32))
                    self.documents[doc_id] = {
                        'text': clean_text,
                        'metadata': metadata or {}
                    }
                    source_type = metadata.get('source_type', 'unknown') if metadata else 'unknown'
                    self.document_counts[source_type] += 1
                    logger.debug(f"Successfully added document {doc_id} after cleaning")
                    return doc_id
            except Exception as retry_error:
                logger.exception(f"Error during retry: {str(retry_error)}")
            
            # If we couldn't recover, raise the original exception
            raise
    
    def search(self, query, top_k=5):
        """
        Search for documents similar to the query using a hybrid approach
        that combines semantic search with basic keyword matching.
        
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
            
            # Perform semantic search with a larger k to increase recall
            initial_k = min(top_k * 5, len(self.documents))  # Increased from 3x to 5x for better recall
            distances, indices = self.index.search(
                np.array([query_embedding], dtype=np.float32), initial_k
            )
            
            # Format initial results
            initial_results = []
            for i, idx in enumerate(indices[0]):
                if idx < 0 or idx >= len(self.documents):
                    continue
                
                # Get document by index
                doc_id = list(self.documents.keys())[idx]
                doc = self.documents[doc_id]
                
                # Make sure metadata is properly initialized
                if 'metadata' not in doc or not doc['metadata']:
                    doc['metadata'] = {}
                
                # Log individual document for debugging
                source_type = doc['metadata'].get('source_type', 'unknown')
                logger.debug(f"Retrieved document: id={doc_id}, type={source_type}, "
                            f"title={doc['metadata'].get('title', 'unknown')}")
                
                # Add to results
                initial_results.append({
                    'id': doc_id,
                    'text': doc['text'],
                    'metadata': doc['metadata'],
                    'score': float(distances[0][i])
                })
            
            # Log sources before reranking
            source_types = {}
            for result in initial_results:
                source_type = result['metadata'].get('source_type', 'unknown')
                source_types[source_type] = source_types.get(source_type, 0) + 1
            
            logger.debug(f"Initial search results by source type: {source_types}")
            
            # Ensure we have a mix of sources if available
            website_results = [r for r in initial_results if r['metadata'].get('source_type') == 'website']
            pdf_results = [r for r in initial_results if r['metadata'].get('source_type') == 'pdf']
            
            if website_results:
                logger.debug(f"Found {len(website_results)} website results")
            if pdf_results:
                logger.debug(f"Found {len(pdf_results)} PDF results")
            
            # Pre-process query for keyword matching
            query_tokens = set(word.lower() for word in query.split())
            
            # Re-rank results using keyword matching with improved weighting
            for result in initial_results:
                # Count keyword matches
                text_tokens = set(word.lower() for word in result['text'].split())
                keyword_matches = len(query_tokens.intersection(text_tokens))
                
                # Apply boost based on keyword matches and source type
                source_type = result['metadata'].get('source_type', 'unknown')
                
                # Base boost from keyword matches
                if keyword_matches > 0:
                    # More significant boost for more keyword matches
                    boost_factor = 0.15 * keyword_matches
                    result['score'] = max(0, result['score'] - boost_factor)  # Lower score is better
                
                # Apply a small boost to website sources to counterbalance any bias
                if source_type == 'website':
                    website_boost = 0.05  # Small boost to website sources
                    result['score'] = max(0, result['score'] - website_boost)
                    logger.debug(f"Applied website boost to result: {result['metadata'].get('title', 'unknown')}")
            
            # Sort by adjusted score
            sorted_results = sorted(initial_results, key=lambda x: x['score'])
            
            # Try to ensure source diversity: include at least one website source if available
            final_results = []
            has_website = any(r['metadata'].get('source_type') == 'website' for r in sorted_results[:top_k])
            
            if not has_website and website_results:
                # Add the highest-ranked website result
                best_website = sorted(website_results, key=lambda x: x['score'])[0]
                logger.debug(f"Ensuring website diversity by adding: {best_website['metadata'].get('title', 'unknown')}")
                final_results.append(best_website)
                # Fill remaining slots from sorted results, avoiding duplicates
                for r in sorted_results:
                    if r['id'] != best_website['id'] and len(final_results) < top_k:
                        final_results.append(r)
            else:
                # Just use top k sorted results
                final_results = sorted_results[:top_k]
            
            # Log final results by source type
            final_source_types = {}
            for result in final_results:
                source_type = result['metadata'].get('source_type', 'unknown')
                final_source_types[source_type] = final_source_types.get(source_type, 0) + 1
                # Log metadata for debugging
                logger.debug(f"Final result: type={source_type}, "
                           f"title={result['metadata'].get('title', 'unknown')}, "
                           f"score={result['score']}")
            
            logger.debug(f"Final search results by source type: {final_source_types}")
            logger.debug(f"Search returned {len(final_results)} results from initial pool of {len(initial_results)}")
            
            return final_results
        except Exception as e:
            logger.exception(f"Error searching vector store: {str(e)}")
            raise
    
    def get_stats(self):
        """
        Get statistics about the vector store.
        
        Returns:
            dict: Statistics about the vector store
        """
        # Count unique PDF sources
        pdf_sources = set()
        website_sources = set()
        
        for doc_id, doc in self.documents.items():
            if doc['metadata'].get('source_type') == 'pdf':
                # Use the title as a unique identifier for PDFs
                pdf_sources.add(doc['metadata'].get('title', 'unknown'))
            elif doc['metadata'].get('source_type') == 'website':
                # Use the URL as a unique identifier for websites
                website_sources.add(doc['metadata'].get('url', 'unknown'))
        
        return {
            'total_documents': len(self.documents),
            'chunks': len(self.documents),
            'websites': len(website_sources),
            'pdfs': len(pdf_sources)
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
