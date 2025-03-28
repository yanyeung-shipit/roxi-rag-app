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
        # Use a larger initial search pool to ensure we find relevant content for disease-specific queries
        initial_k_multiplier = 5
        try:
            if len(self.documents) == 0:
                logger.warning("Search performed on empty vector store")
                return []
            
            # Generate embedding for the query
            query_embedding = self._get_embedding(query)
            
            # Perform semantic search with a larger k to increase recall
            initial_k = min(top_k * initial_k_multiplier, len(self.documents))
            logger.debug(f"Using initial_k={initial_k} with multiplier={initial_k_multiplier} for query: {query[:30]}...")
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
                # Log website results with page numbers for multi-page crawl debugging
                for wr in website_results[:3]:  # Log first 3 for debugging
                    url = wr['metadata'].get('url', 'unknown')
                    page_num = wr['metadata'].get('page_number', 'main page')
                    logger.debug(f"Website result: {url} (Page: {page_num})")
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
                
                # Apply stronger boosts to website sources to better utilize website content
                if source_type == 'website':
                    # Base boost for any website source
                    website_boost = 0.15  # Increased from 0.10 to 0.15 to further prioritize websites
                    
                    # Check if the text contains navigation elements which indicate a website covering topic areas
                    if "Menu/Navigation:" in result['text'] or "Header:" in result['text']:
                        # Stronger boost for navigation/menu content which is very valuable for determining site topics
                        nav_boost = 0.12  # Increased from 0.10 to 0.12
                        website_boost += nav_boost
                        logger.debug(f"Applied navigation boost to: {result['metadata'].get('title', 'unknown')}")
                    
                    # Check for specific topic URL patterns which should be highly prioritized
                    url = result['metadata'].get('url', '')
                    is_topic_url = False
                    topic_patterns = ['/topic/', '/disease/', '/diseases/', '/condition/', '/conditions/']
                    if any(pattern in url for pattern in topic_patterns):
                        is_topic_url = True
                        topic_boost = 0.25  # Significant boost for topic-specific URLs
                        website_boost += topic_boost
                        logger.debug(f"Applied special topic page boost for URL: {url} - boost: {topic_boost}")
                        
                        # For topic pages like '/topic/myositis/', extract the specific disease/topic name
                        topic_name = None
                        for pattern in topic_patterns:
                            if pattern in url:
                                parts = url.split(pattern)
                                if len(parts) > 1 and parts[1]:
                                    topic_name = parts[1].strip('/').replace('-', ' ').replace('_', ' ')
                                    break
                        
                        # If we found a specific topic name and it's in the query, give even more boost
                        if topic_name and any(topic_part in query.lower() for topic_part in topic_name.lower().split()):
                            query_topic_match_boost = 0.35
                            website_boost += query_topic_match_boost
                            logger.debug(f"Applied query-topic match boost for topic: {topic_name} - boost: {query_topic_match_boost}")
                                                
                    # Additional boost for pages with specific page numbers from multi-page crawls
                    # These are likely more specific content pages rather than general homepage content
                    if 'page_number' in result['metadata'] and result['metadata']['page_number'] is not None:
                        page_num = result['metadata']['page_number']
                        # Progressive boost based on page number - emphasize specific content pages
                        if page_num > 1:  # Not the main page
                            page_boost = min(0.18, 0.06 * page_num)  # Increased from 0.15 to 0.18 max boost
                            website_boost += page_boost
                            logger.debug(f"Applied additional page boost for page {page_num}: {page_boost}")
                    
                    # Check if website text contains terms related to the query
                    query_tokens = set(word.lower() for word in query.split())
                    if any(token in result['text'].lower() for token in query_tokens):
                        relevance_boost = 0.10  # Increased from 0.08 to 0.10
                        website_boost += relevance_boost
                        logger.debug(f"Applied query term relevance boost: {relevance_boost}")
                    
                    # Special boost for disease-specific content
                    # These terms are common in rheumatology disease pages, expanded to include more conditions
                    disease_terms = [
                        # Common inflammatory arthritides
                        "rheumatoid arthritis", "ra", "psoriatic arthritis", "psa", "ankylosing spondylitis", "as",
                        "axial spondyloarthritis", "peripheral spondyloarthritis", "spondyloarthritis", 
                        "reactive arthritis", "inflammatory arthritis",
                        
                        # Connective tissue diseases
                        "lupus", "sle", "systemic lupus erythematosus", "scleroderma", "systemic sclerosis", "ssc",
                        "myositis", "dermatomyositis", "polymyositis", "inclusion body myositis", 
                        "sjögren", "sjogren", "sjögrens", "sjogrens", "mixed connective tissue disease", "mctd",
                        "undifferentiated connective tissue disease", "uctd", "connective tissue disease",
                        
                        # Vasculitides
                        "vasculitis", "giant cell arteritis", "gca", "takayasus", "polyarteritis nodosa", 
                        "kawasaki", "anca vasculitis", "granulomatosis with polyangiitis", "gpa", "wegeners",
                        "microscopic polyangiitis", "mpa", "eosinophilic granulomatosis", "egpa", "churg strauss",
                        "igg4", "igg4-related disease", "igg4-rd", "behcets",
                        
                        # Autoinflammatory conditions
                        "stills disease", "juvenile idiopathic arthritis", "periodic fever syndrome",
                        "familial mediterranean fever", "cryopyrin associated periodic syndrome", "caps",
                        
                        # Crystal arthropathies
                        "gout", "calcium pyrophosphate deposition", "cppd", "pseudogout", "crystal arthritis",
                        
                        # Other rheumatic conditions
                        "osteoarthritis", "oa", "fibromyalgia", "polymyalgia rheumatica", "pmr",
                        "autoimmune", "uveitis", "sarcoidosis", "anti-phospholipid syndrome", "aps",
                        "relapsing polychondritis", "raynauds", "arthritis", "rheumatic"
                    ]
                    
                    # Check if any disease terms are in the text (case insensitive)
                    text_lower = result['text'].lower()
                    found_disease_terms = [term for term in disease_terms if term in text_lower]
                    
                    # Check for disease terms in the URL or page title
                    url = result['metadata'].get('url', '').lower()
                    title = result['metadata'].get('title', '').lower()
                    
                    # Check if URL contains disease-specific patterns common in rheumatology websites
                    url_disease_indicators = any(pattern in url for pattern in [
                        "topic/", "disease/", "condition/", "chapters/", "articles/", 
                        "rheumatoid", "lupus", "arthritis", "myositis", "sjogren", "vasculitis"
                    ])
                    
                    # Combine found terms with URL indicators for stronger boost for actual disease pages
                    if found_disease_terms or url_disease_indicators:
                        # Apply stronger boost for disease-specific content
                        disease_boost = 0.15 + (0.03 * len(found_disease_terms))  # Base + additional for more terms
                        
                        # Extra boost for disease terms in URL or title (likely more relevant page)
                        if url_disease_indicators:
                            disease_boost += 0.10  # Significant boost for disease-specific URLs
                            logger.debug(f"Applied URL disease pattern boost: {url}")
                            
                        # Additional boost if disease terms are found in title
                        title_disease_terms = [term for term in disease_terms if term in title]
                        if title_disease_terms:
                            disease_boost += 0.08  # Good boost for disease terms in title
                            logger.debug(f"Applied title disease term boost: {title}")
                        
                        # Apply additional boost for content that directly matches keywords in the query
                        # This helps any disease-specific query, not just a specific condition
                        for token in query_tokens:
                            # Check if this query term is a disease term and it appears in the text
                            if token in text_lower and any(token in disease_term for disease_term in disease_terms):
                                query_match_boost = 0.15  # Good boost for directly matching disease terms
                                disease_boost += query_match_boost
                                logger.debug(f"Applied query-disease term match boost: {query_match_boost} for term: {token}")
                                break  # Only apply this boost once
                        
                        disease_boost = min(0.30, disease_boost)  # Cap the boost at a reasonable level
                        website_boost += disease_boost
                        logger.debug(f"Applied disease-specific boost: {disease_boost} for terms: {found_disease_terms[:3]}")
                    
                    # Apply the combined boost
                    result['score'] = max(0, result['score'] - website_boost)
                    logger.debug(f"Applied combined website boost of {website_boost} to: {result['metadata'].get('title', 'unknown')}")
            
            # Sort by adjusted score
            sorted_results = sorted(initial_results, key=lambda x: x['score'])
            
            # Enhanced diversity logic - ALWAYS include at least one website source if available
            final_results = []
            
            # First, check if any website sources are already in the top results
            top_website_results = [r for r in sorted_results[:top_k] if r['metadata'].get('source_type') == 'website']
            has_website_in_top = len(top_website_results) > 0
            
            # Ensure we ALWAYS have at least one website source if any are available
            if not has_website_in_top and website_results:
                # Sort website results by score
                sorted_website_results = sorted(website_results, key=lambda x: x['score'])
                
                # Prioritize website results that have navigation elements (they're more informative)
                nav_website_results = [r for r in sorted_website_results if "Menu/Navigation:" in r['text'] or "Header:" in r['text']]
                
                if nav_website_results:
                    # Use the highest scoring navigation-containing website
                    best_website = nav_website_results[0]
                    logger.debug(f"Ensuring website diversity by adding navigation-rich source: {best_website['metadata'].get('title', 'unknown')}")
                else:
                    # Use the highest scoring website
                    best_website = sorted_website_results[0]
                    logger.debug(f"Ensuring website diversity by adding: {best_website['metadata'].get('title', 'unknown')}")
                
                # Add to final results
                final_results.append(best_website)
                
                # Fill remaining slots from sorted results, avoiding duplicates
                for r in sorted_results:
                    if r['id'] != best_website['id'] and len(final_results) < top_k:
                        final_results.append(r)
            elif has_website_in_top:
                # Website already in top results naturally
                logger.debug(f"Website source(s) already in top {top_k} results: {len(top_website_results)} website sources")
                final_results = sorted_results[:top_k]
            else:
                # No website sources available or all websites already excluded
                logger.debug("No website sources available to include in results")
                final_results = sorted_results[:top_k]
                
            # Ensure we prioritize diversity in the top 3 results
            if len(final_results) >= 3:
                # Check source types in top 3
                top_3_types = [r['metadata'].get('source_type') for r in final_results[:3]]
                
                # If all top 3 are the same type, try to promote a different type
                if len(set(top_3_types)) == 1:
                    logger.debug(f"All top 3 results are {top_3_types[0]} sources, attempting to diversify")
                    
                    # Find the first result of a different type
                    different_type_idx = next((i for i, r in enumerate(final_results) 
                                            if r['metadata'].get('source_type') != top_3_types[0] and i >= 3), None)
                    
                    if different_type_idx is not None:
                        # Swap to ensure diversity in top 3
                        final_results[2], final_results[different_type_idx] = final_results[different_type_idx], final_results[2]
                        logger.debug(f"Promoted a {final_results[2]['metadata'].get('source_type')} source to position 3 for diversity")
            
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
                # For multi-page crawls, pages from the same domain count as one website source
                url = doc['metadata'].get('url', 'unknown')
                # Extract domain from URL for unique counting
                try:
                    domain = '/'.join(url.split('/')[:3])  # Get schema + domain
                    website_sources.add(domain)
                except:
                    website_sources.add(url)
        
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
    
    def remove_document(self, document_id):
        """
        Remove all chunks for a specific document from the vector store.
        
        Args:
            document_id (int): ID of the document to remove
            
        Returns:
            int: Number of chunks removed
        """
        try:
            # Convert document_id to string for comparison
            doc_id_str = str(document_id)
            
            # Find all chunks that belong to this document
            chunks_to_remove = []
            for i, (doc_key, doc) in enumerate(list(self.documents.items())):
                metadata = doc.get('metadata', {})
                
                # Check if this chunk belongs to the document we want to remove
                if metadata.get('document_id') == document_id:
                    chunks_to_remove.append((i, doc_key))
                    
            if not chunks_to_remove:
                logger.warning(f"No chunks found for document_id {document_id} in vector store")
                return 0
                
            logger.info(f"Removing {len(chunks_to_remove)} chunks for document_id {document_id}")
            
            # Sort in reverse order to avoid index shifting issues
            chunks_to_remove.sort(reverse=True)
            
            # Since FAISS doesn't support direct removal, we need to rebuild the index
            # First, collect all embeddings to keep
            embeddings_to_keep = []
            new_documents = {}
            
            # Get all embeddings from the index
            all_embeddings = np.zeros((self.index.ntotal, self.dimension), dtype=np.float32)
            faiss.extract_index_vectors(self.index, all_embeddings)
            
            # Track indices to remove
            indices_to_remove = set([idx for idx, _ in chunks_to_remove])
            
            # Keep track of the mapping from old to new indices
            old_to_new_idx = {}
            new_idx = 0
            
            # For each document that we want to keep
            for old_idx, (doc_key, doc) in enumerate(self.documents.items()):
                if old_idx not in indices_to_remove:
                    # Keep this embedding
                    embeddings_to_keep.append(all_embeddings[old_idx])
                    
                    # Update the documents dictionary
                    new_documents[doc_key] = doc
                    
                    # Update the index mapping
                    old_to_new_idx[old_idx] = new_idx
                    new_idx += 1
            
            # Create a new index with the remaining embeddings
            self.index = faiss.IndexFlatL2(self.dimension)
            if embeddings_to_keep:
                self.index.add(np.array(embeddings_to_keep))
            
            # Update the documents dictionary
            self.documents = new_documents
            
            # Update document counts
            # This is more complex as we'd need to know the source type, simplifying for now
            self.document_counts = defaultdict(int)
            for doc in self.documents.values():
                source_type = doc.get('metadata', {}).get('source_type', 'unknown')
                self.document_counts[source_type] += 1
            
            # Save the updated index and data
            self._save()
            
            logger.info(f"Successfully removed document {document_id} from vector store")
            return len(chunks_to_remove)
            
        except Exception as e:
            logger.exception(f"Error removing document from vector store: {str(e)}")
            return 0
    
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
