import os
import logging
import numpy as np
import faiss
import pickle
import uuid
import time
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
            
    def unload_from_memory(self):
        """
        MAXIMUM MEMORY RELEASE unload function for vector store to achieve 
        the absolute minimum memory footprint possible. This implementation
        employs every available technique to ensure complete memory release.
        
        Returns:
            int: Number of documents unloaded
        """
        try:
            # Record memory before cleanup for comparison
            pmem_before = None
            try:
                import psutil
                process = psutil.Process()
                pmem_before = process.memory_info()
                mem_before_mb = pmem_before.rss / (1024 * 1024)
                logger.warning(f"Memory before vector store unload: {mem_before_mb:.1f}MB")
            except:
                pass
            
            # Save current state first to ensure we don't lose data
            self._save()
            
            # Get the current count for reporting
            doc_count = len(self.documents)
            
            logger.warning(f"MAXIMUM MEMORY RELEASE: unloading vector store with {doc_count} documents")
            
            # -------------------- STAGE 1: Clear the largest memory consumers first --------------------
            
            # Start by removing the largest memory consumers - the embeddings
            # Get a snapshot of document IDs to avoid dictionary size change during iteration
            doc_ids = list(self.documents.keys())
            
            for doc_id in doc_ids:
                # Set all embeddings to None (these consume the most memory by far)
                if 'embedding' in self.documents[doc_id]:
                    self.documents[doc_id]['embedding'] = None
                
                # Truncate all text content to absolute minimum
                if 'text' in self.documents[doc_id] and isinstance(self.documents[doc_id]['text'], str):
                    # Just keep a minimal identification fragment
                    self.documents[doc_id]['text'] = self.documents[doc_id]['text'][:20] + "..."
                
                # Strip metadata to bare essentials
                if 'metadata' in self.documents[doc_id] and isinstance(self.documents[doc_id]['metadata'], dict):
                    # Start with empty dict and just keep required identifiers
                    essential_keys = ['doc_id', 'id', 'document_id', 'type', 'chunk_id']
                    minimal_metadata = {}
                    for key in essential_keys:
                        if key in self.documents[doc_id]['metadata']:
                            minimal_metadata[key] = self.documents[doc_id]['metadata'][key]
                    
                    # Replace with minimal version
                    self.documents[doc_id]['metadata'] = minimal_metadata
            
            # Immediate interim garbage collection to free memory from large objects
            import gc
            gc.collect(generation=2)
            
            # -------------------- STAGE 2: Replace all data structures --------------------
            
            # Instead of clearing, we replace all collections to ensure memory is fully released
            # Save references to old structures to explicitly delete them
            old_documents = self.documents
            old_counts = self.document_counts
            old_index = self.index
            
            # Create brand new structures
            self.documents = {}
            self.document_counts = defaultdict(int)
            self.index = faiss.IndexFlatL2(self.dimension)
            
            # Explicitly delete old structures to release their memory
            del old_documents
            del old_counts
            del old_index
            
            # -------------------- STAGE 3: Clear all caches and temp data --------------------
            
            # Systematically identify and clear all caches
            cache_attributes = [
                attr for attr in dir(self) 
                if ('cache' in attr.lower() or 'temp' in attr.lower() or 'buffer' in attr.lower())
                and not attr.startswith('__')
            ]
            
            for attr_name in cache_attributes:
                try:
                    # Get the current value
                    cache_obj = getattr(self, attr_name)
                    
                    # Handle different types of cache objects
                    if isinstance(cache_obj, dict):
                        # Replace with new empty dict
                        setattr(self, attr_name, {})
                    elif isinstance(cache_obj, list):
                        # Replace with new empty list
                        setattr(self, attr_name, [])
                    elif isinstance(cache_obj, set):
                        # Replace with new empty set
                        setattr(self, attr_name, set())
                    else:
                        # Set to None for other types
                        setattr(self, attr_name, None)
                        
                    logger.debug(f"Cleared vector store cache: {attr_name}")
                except Exception as e:
                    logger.debug(f"Error clearing cache {attr_name}: {str(e)}")
            
            # Explicitly clear known caches
            self._processed_chunk_ids_cache = None
            self._last_cache_update_time = 0
            
            if hasattr(self, '_search_cache'):
                self._search_cache = {}
            
            if hasattr(self, '_document_lookup_cache'):
                self._document_lookup_cache = {}
            
            if hasattr(self, '_result_cache'):
                self._result_cache = {}
            
            # -------------------- STAGE 4: Aggressive garbage collection --------------------
            
            # Run a multi-phase garbage collection strategy
            # First collect all generations with debug logging
            logger.debug("Running multi-phase garbage collection")
            gc.collect(generation=2)
            gc.collect(generation=1)
            gc.collect(generation=0)
            
            # -------------------- STAGE 5: Safe reference cycle breaking --------------------
            
            # The previous approach was too aggressive and caused crashes
            # This version is more selective and safer
            logger.debug("Performing targeted cycle breaking")
            
            # Only clear specific dictionaries we know are safe to clear
            # Rather than iterating all objects which can cause crashes
            cycle_count = 0
            
            # Clear caches in the gc module itself
            try:
                if hasattr(gc, 'garbage'):
                    orig_len = len(gc.garbage)
                    gc.garbage.clear()
                    cycle_count += 1
                    logger.debug(f"Cleared {orig_len} objects from gc.garbage")
            except:
                pass
                
            # Focus on clearing only our own data structures
            # This is much safer than trying to clear arbitrary objects
            try:
                # Any temporary local variables/data structures we can safely clear
                local_objects_to_clear = []
                
                # Clear these objects safely
                for obj in local_objects_to_clear:
                    if isinstance(obj, dict):
                        obj.clear()
                        cycle_count += 1
                    elif isinstance(obj, list):
                        obj.clear()
                        cycle_count += 1
                    elif isinstance(obj, set):
                        obj.clear()
                        cycle_count += 1
            except:
                pass
            
            logger.debug(f"Safely cleared {cycle_count} potential reference cycles")
            
            # Additional garbage collection after breaking cycles
            gc.collect(generation=2)
            
            # -------------------- STAGE 6: Basic OS-level memory release --------------------
            
            # Simplified approach to avoid crashes
            try:
                # Import modules safely
                import ctypes
                import os
                
                # OS-specific memory trimming
                if os.name == 'posix':  # Linux/Unix
                    # 1. Use malloc_trim to release memory back to the OS
                    try:
                        # Load the C library
                        libc = ctypes.CDLL('libc.so.6')
                        
                        # Check if malloc_trim exists
                        if hasattr(libc, 'malloc_trim'):
                            # Call it once and log result
                            trim_result = libc.malloc_trim(0)
                            
                            # Log the result safely
                            logger.warning(f"OS memory release: malloc_trim called, result={trim_result}")
                    except Exception as e:
                        logger.debug(f"malloc_trim not available: {e}")
                    
                    # 2. Set OOM score - simpler approach
                    try:
                        # Set this process as a candidate for OOM killing if memory pressure occurs
                        with open('/proc/self/oom_score_adj', 'w') as f:
                            f.write('500')  # Moderate value to avoid immediate killing
                        logger.debug("Set moderate OOM score for memory pressure handling")
                    except:
                        # This is non-critical, we can continue without it
                        pass
            except Exception as e:
                # Log failure but continue
                logger.debug(f"Basic OS-level memory release failed: {str(e)}")
            
            # -------------------- STAGE 7: Memory measurement and reporting --------------------
            
            # Record memory after cleanup
            try:
                if pmem_before is not None:
                    import psutil
                    process = psutil.Process()
                    pmem_after = process.memory_info()
                    mem_after_mb = pmem_after.rss / (1024 * 1024)
                    memory_freed = (pmem_before.rss - pmem_after.rss) / (1024 * 1024)
                    
                    # Calculate before memory values safely
                    mem_before_mb = pmem_before.rss / (1024 * 1024)
                    
                    # Log memory statistics
                    logger.warning(
                        f"VECTOR STORE MEMORY: Before={mem_before_mb:.1f}MB, "
                        f"After={mem_after_mb:.1f}MB, "
                        f"Freed={memory_freed:.1f}MB"
                    )
            except Exception as e:
                logger.debug(f"Error logging memory statistics: {e}")
            
            logger.warning(f"VECTOR STORE MAXIMUM MEMORY RELEASE COMPLETE: {doc_count} documents unloaded")
            return doc_count
            
        except Exception as e:
            logger.exception(f"Error unloading vector store: {str(e)}")
            return 0
            
    def reload_from_disk(self):
        """
        Reload the vector store from disk.
        This is used to restore the vector store after it was unloaded.
        
        Returns:
            int: Number of documents loaded
        """
        try:
            # First make sure we're starting with empty data structures
            self.documents = {}
            self.document_counts = defaultdict(int)
            self.index = faiss.IndexFlatL2(self.dimension)
            
            # Load from disk
            self._load_if_exists()
            
            # Return the number of documents loaded
            return len(self.documents)
        except Exception as e:
            logger.exception(f"Error reloading vector store: {str(e)}")
            return 0
    
    def _save(self):
        """Save the current index and data to disk with improved error handling."""
        # Use temporary files to avoid corruption if the process is interrupted
        temp_index_path = f"{self.index_path}.temp"
        temp_data_path = f"{self.data_path}.temp"
        
        try:
            # First, write to temporary files
            logger.debug("Writing vector index to temporary file")
            try:
                faiss.write_index(self.index, temp_index_path)
            except Exception as index_error:
                logger.error(f"Failed to write index file: {str(index_error)}")
                # Clean up temp file if it exists
                if os.path.exists(temp_index_path):
                    os.remove(temp_index_path)
                # Don't raise, continue with data file
            
            logger.debug("Writing document data to temporary file")
            try:
                with open(temp_data_path, 'wb') as f:
                    pickle.dump({
                        'documents': self.documents,
                        'document_counts': self.document_counts
                    }, f)
            except Exception as data_error:
                logger.error(f"Failed to write data file: {str(data_error)}")
                # Clean up temp files
                if os.path.exists(temp_data_path):
                    os.remove(temp_data_path)
                if os.path.exists(temp_index_path):
                    os.remove(temp_index_path)
                # Don't raise, at least we tried
            
            # Now rename temporary files to final names
            logger.debug("Renaming temporary files to final names")
            if os.path.exists(temp_index_path):
                # Backup existing file if it exists
                if os.path.exists(self.index_path):
                    backup_index = f"{self.index_path}.bak"
                    if os.path.exists(backup_index):
                        os.remove(backup_index)  # Remove old backup if it exists
                    os.rename(self.index_path, backup_index)
                # Move temp file to final name
                os.rename(temp_index_path, self.index_path)
            
            if os.path.exists(temp_data_path):
                # Backup existing file if it exists
                if os.path.exists(self.data_path):
                    backup_data = f"{self.data_path}.bak"
                    if os.path.exists(backup_data):
                        os.remove(backup_data)  # Remove old backup if it exists
                    os.rename(self.data_path, backup_data)
                # Move temp file to final name
                os.rename(temp_data_path, self.data_path)
            
            logger.debug("Vector store saved to disk successfully")
            
        except Exception as e:
            logger.exception(f"Error in vector store save process: {str(e)}")
            # Try to clean up any temporary files
            for path in [temp_index_path, temp_data_path]:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except:
                        pass
            # Note: we deliberately don't raise the exception to avoid crashing the server
    
    def save(self):
        """Public method to explicitly save the vector store to disk."""
        self._save()
        
    def add_embedding(self, text, embedding, metadata=None):
        """
        Add text with a pre-computed embedding to the vector store.
        
        Args:
            text (str): Text content to add
            embedding (list): Pre-computed embedding vector
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
            
            # Create a unique ID for this document
            doc_id = str(uuid.uuid4())
            
            # Store text and metadata
            self.documents[doc_id] = {
                "text": text,
                "metadata": metadata or {}
            }
            
            # Convert embedding to numpy array
            embedding_array = np.array([embedding], dtype=np.float32)
            
            # Add to index
            faiss.normalize_L2(embedding_array)
            self.index.add(embedding_array)
            
            # Update document type counts
            doc_type = metadata.get("source_type", "unknown") if metadata else "unknown"
            self.document_counts[doc_type] += 1
            
            # Return the document ID
            return doc_id
            
        except Exception as e:
            logger.error(f"Error adding embedding: {e}")
            return None
        
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
            if metadata and 'formatted_citation' in metadata:
                logger.debug(f"Adding document to vector store with formatted_citation: {metadata['formatted_citation']}")
            else:
                if metadata:
                    logger.debug(f"Adding document to vector store WITHOUT formatted_citation, metadata keys: {list(metadata.keys())}")
                else:
                    logger.debug("Adding document to vector store with NO metadata")
                
            self.documents[doc_id] = {
                'text': text,
                'metadata': metadata or {}
            }
            
            # Update document counts
            source_type = metadata.get('source_type', 'unknown') if metadata else 'unknown'
            self.document_counts[source_type] += 1
            
            # Save updated index and data with less frequency to avoid IO errors during bulk operations
            # Only save every 25 documents or after processing small batches of pdfs/websites
            if len(self.documents) % 25 == 0:
                logger.debug(f"Saving vector store after {len(self.documents)} documents")
                self._save()
            elif source_type in ['website', 'pdf'] and len(self.documents) % 5 == 0:
                # For important document types, save more frequently but still batch them
                logger.debug(f"Saving vector store after adding {source_type} document")
                self._save()
            
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
    
    # Cache for processed chunk IDs
    _processed_chunk_ids_cache = None
    _last_cache_update_time = 0
    _cache_ttl = 60  # Cache time-to-live in seconds
    
    def get_processed_chunk_ids(self, force_refresh=False):
        """
        Get the set of chunk IDs that have been processed and added to the vector store.
        Uses a caching mechanism to avoid frequent recomputations.
        
        Args:
            force_refresh (bool): If True, ignore the cache and recalculate
            
        Returns:
            set: Set of processed chunk IDs
        """
        current_time = time.time()
        
        # Make sure cache attributes are initialized
        if not hasattr(self, '_processed_chunk_ids_cache') or self._processed_chunk_ids_cache is None:
            self._processed_chunk_ids_cache = set()
            
        if not hasattr(self, '_last_cache_update_time') or self._last_cache_update_time is None:
            self._last_cache_update_time = 0
            
        if not hasattr(self, '_cache_ttl') or self._cache_ttl is None:
            self._cache_ttl = 5.0  # Default TTL of 5 seconds
            
        # Check if we can use the cached value
        if not force_refresh and self._processed_chunk_ids_cache is not None:
            # Safely check if cache is fresh (within TTL)
            try:
                if current_time - self._last_cache_update_time < self._cache_ttl:
                    return self._processed_chunk_ids_cache
            except (TypeError, ValueError) as e:
                logger.debug(f"Cache time calculation error: {e}, regenerating cache")
                # Continue to regenerate cache
        
        # Need to recompute the processed IDs
        processed_ids = set()
        
        for doc_id, doc in self.documents.items():
            metadata = doc.get('metadata', {})
            if 'chunk_id' in metadata and metadata['chunk_id'] is not None:
                # Ensure it's an integer
                try:
                    chunk_id = int(metadata['chunk_id'])
                    processed_ids.add(chunk_id)
                except (ValueError, TypeError):
                    # Skip invalid chunk IDs
                    pass
        
        # Update the cache
        self._processed_chunk_ids_cache = processed_ids
        self._last_cache_update_time = current_time
        
        # Only log when we actually recompute
        logger.info(f"Found {len(processed_ids)} processed chunk IDs in vector store")
        return processed_ids
    
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
    
    def remove_document_by_url(self, url_pattern):
        """
        Remove all chunks for documents with URLs matching a specific pattern.
        
        Args:
            url_pattern (str): URL pattern to match
            
        Returns:
            int: Number of chunks removed
        """
        try:
            # Enhanced debugging for document removal
            logger.info(f"Starting removal of documents with URL pattern '{url_pattern}' from vector store")
            logger.info(f"Current vector store status: {len(self.documents)} total chunks, index size: {self.index.ntotal}")
            
            # Find all chunks with matching URL pattern
            chunks_to_remove = []
            for i, (doc_key, doc) in enumerate(list(self.documents.items())):
                metadata = doc.get('metadata', {})
                
                # Check if URL contains the pattern
                url = metadata.get('url', '')
                if url_pattern in url:
                    logger.info(f"Marking chunk for removal by URL pattern match: {doc_key}, url={url}")
                    chunks_to_remove.append((i, doc_key))
            
            if not chunks_to_remove:
                logger.warning(f"No chunks found with URL pattern '{url_pattern}' in vector store")
                return 0
            
            # Process removal logic (same as in remove_document)
            return self._process_chunk_removal(chunks_to_remove)
            
        except Exception as e:
            logger.exception(f"Error removing document by URL pattern: {str(e)}")
            return 0
    
    def _process_chunk_removal(self, chunks_to_remove):
        """
        Process the removal of chunks from the vector store.
        
        Args:
            chunks_to_remove (list): List of (index, doc_key) tuples to remove
            
        Returns:
            int: Number of chunks removed
        """
        try:
            logger.info(f"Removing {len(chunks_to_remove)} chunks from vector store")
            
            # Sort in reverse order to avoid index shifting issues
            chunks_to_remove.sort(reverse=True)
            
            # Since FAISS doesn't support direct removal, we need to rebuild the index
            # First, collect all embeddings to keep
            embeddings_to_keep = []
            new_documents = {}
            
            # Get all embeddings from the index
            # For compatibility with different FAISS versions
            try:
                # Method in newer FAISS versions
                all_embeddings = np.zeros((self.index.ntotal, self.dimension), dtype=np.float32)
                faiss.extract_index_vectors(self.index, all_embeddings)
            except (AttributeError, NotImplementedError):
                # Fall back to reconstructing vectors for older FAISS versions
                logger.info("Using reconstruction method for FAISS vector extraction")
                all_embeddings = np.zeros((self.index.ntotal, self.dimension), dtype=np.float32)
                for i in range(self.index.ntotal):
                    all_embeddings[i] = self.index.reconstruct(i)
            
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
            
            logger.info(f"Successfully removed {len(chunks_to_remove)} chunks from vector store")
            logger.info(f"New vector store status: {len(self.documents)} total chunks, index size: {self.index.ntotal}")
            
            return len(chunks_to_remove)
            
        except Exception as e:
            logger.exception(f"Error processing chunk removal: {str(e)}")
            return 0
    
    def remove_document_by_filename(self, filename):
        """
        Remove all chunks for a document by filename pattern.
        
        Args:
            filename (str): Filename (or part of filename) to match against
            
        Returns:
            int: Number of chunks removed
        """
        try:
            logger.info(f"Removing documents with filename pattern: {filename}")
            
            # Find all chunks with matching filename
            chunks_to_remove = []
            file_paths_to_remove = set()
            
            for i, (doc_key, doc) in enumerate(list(self.documents.items())):
                metadata = doc.get('metadata', {})
                
                # Check for filename in various metadata fields
                doc_filename = metadata.get('filename', '')
                file_path = metadata.get('file_path', '')
                title = metadata.get('title', '')
                citation = metadata.get('citation', '')
                
                # If filename appears in any of these fields, mark for removal
                if (filename in doc_filename or 
                    filename in file_path or 
                    filename in title or 
                    filename in citation):
                    logger.info(f"Marking chunk for removal by filename match: {doc_key}")
                    chunks_to_remove.append((i, doc_key))
                    
                    # Remember file path for additional cleanup
                    if file_path:
                        file_paths_to_remove.add(file_path)
            
            if not chunks_to_remove:
                logger.warning(f"No chunks found matching filename '{filename}' in vector store")
                return 0
                
            # Process the chunk removal
            removed_count = self._process_chunk_removal(chunks_to_remove)
            
            # Also try to remove any chunks with matching file paths
            for file_path in file_paths_to_remove:
                for i, (doc_key, doc) in enumerate(list(self.documents.items())):
                    metadata = doc.get('metadata', {})
                    if metadata.get('file_path') == file_path:
                        logger.info(f"Removing additional chunk with matching file_path: {file_path}")
                        self.documents.pop(doc_key, None)
                        removed_count += 1
            
            logger.info(f"Removed {removed_count} chunks with filename '{filename}' from vector store")
            return removed_count
            
        except Exception as e:
            logger.exception(f"Error removing document by filename from vector store: {str(e)}")
            return 0
    
    def remove_document(self, document_id):
        """
        Remove all chunks for a specific document from the vector store.
        
        Args:
            document_id (int): ID of the document to remove
            
        Returns:
            int: Number of chunks removed
        """
        try:
            # Enhanced debugging for document removal
            logger.info(f"Starting removal of document_id {document_id} from vector store")
            logger.info(f"Current vector store status: {len(self.documents)} total chunks, index size: {self.index.ntotal}")
            
            # Check all document metadata for debugging
            doc_ids_in_store = set()
            url_to_remove = None
            filename_to_remove = None
            file_path_to_remove = None
            
            for i, (doc_key, doc) in enumerate(list(self.documents.items())):
                metadata = doc.get('metadata', {})
                doc_id_in_store = metadata.get('document_id')
                if doc_id_in_store:
                    doc_ids_in_store.add(doc_id_in_store)
                
                # Get document info if we find one matching this ID
                if doc_id_in_store == document_id:
                    if 'url' in metadata:
                        url_to_remove = metadata.get('url', '')
                        logger.info(f"Found URL for document ID {document_id}: {url_to_remove}")
                    if 'filename' in metadata:
                        filename_to_remove = metadata.get('filename', '')
                        logger.info(f"Found filename for document ID {document_id}: {filename_to_remove}")
                    if 'file_path' in metadata:
                        file_path_to_remove = metadata.get('file_path', '')
                        logger.info(f"Found file_path for document ID {document_id}: {file_path_to_remove}")
            
            logger.info(f"Vector store contains chunks from {len(doc_ids_in_store)} distinct document IDs")
            
            # Find all chunks that belong to this document by ID
            chunks_to_remove = []
            for i, (doc_key, doc) in enumerate(list(self.documents.items())):
                metadata = doc.get('metadata', {})
                
                # Check if this chunk belongs to the document we want to remove
                if metadata.get('document_id') == document_id:
                    logger.info(f"Marking chunk for removal by document_id match: {doc_key}")
                    chunks_to_remove.append((i, doc_key))
                    
            if not chunks_to_remove:
                logger.warning(f"No chunks found for document_id {document_id} in vector store")
                
                # If we couldn't find by ID, try other methods
                removed_count = 0
                
                # 1. Try URL pattern for websites
                if url_to_remove and ('rheum.reviews' in url_to_remove):
                    # Extract pattern from the URL (like 'psoriatic-arthritis')
                    url_parts = url_to_remove.split('/')
                    for part in url_parts:
                        if part and len(part) > 5 and '-' in part:  # Likely a slug/pattern
                            pattern = part
                            logger.info(f"Trying to remove by URL pattern: {pattern}")
                            url_removed = self.remove_document_by_url(pattern)
                            if url_removed > 0:
                                logger.info(f"Successfully removed {url_removed} chunks by URL pattern")
                                removed_count += url_removed
                
                # 2. Try filename matching for PDFs
                if filename_to_remove:
                    logger.info(f"Trying to remove by filename: {filename_to_remove}")
                    filename_removed = self.remove_document_by_filename(filename_to_remove)
                    if filename_removed > 0:
                        logger.info(f"Successfully removed {filename_removed} chunks by filename")
                        removed_count += filename_removed
                
                # 3. Try filepath matching for PDFs
                if file_path_to_remove:
                    logger.info(f"Trying to remove by file path: {file_path_to_remove}")
                    # Extract just the filename from the path
                    import os
                    path_filename = os.path.basename(file_path_to_remove)
                    path_removed = self.remove_document_by_filename(path_filename)
                    if path_removed > 0:
                        logger.info(f"Successfully removed {path_removed} chunks by file path")
                        removed_count += path_removed
                
                return removed_count
                
            # Process the chunk removal by document ID
            removed_count = self._process_chunk_removal(chunks_to_remove)
            
            # Try additional removal methods to be thorough
            additional_removed = 0
            
            # 1. Try URL pattern for websites
            if url_to_remove and ('rheum.reviews' in url_to_remove):
                # Extract pattern from the URL (like 'psoriatic-arthritis')
                url_parts = url_to_remove.split('/')
                for part in url_parts:
                    if part and len(part) > 5 and '-' in part:  # Likely a slug/pattern
                        pattern = part
                        logger.info(f"Also removing any matching URL pattern: {pattern}")
                        url_removed = self.remove_document_by_url(pattern)
                        if url_removed > 0:
                            logger.info(f"Successfully removed {url_removed} additional chunks by URL pattern")
                            additional_removed += url_removed
            
            # 2. Try filename matching for PDFs
            if filename_to_remove:
                logger.info(f"Also removing any matching filename: {filename_to_remove}")
                filename_removed = self.remove_document_by_filename(filename_to_remove)
                if filename_removed > 0:
                    logger.info(f"Successfully removed {filename_removed} additional chunks by filename")
                    additional_removed += filename_removed
            
            # 3. Try filepath matching for PDFs
            if file_path_to_remove:
                logger.info(f"Also removing any matching file path: {file_path_to_remove}")
                # Extract just the filename from the path
                import os
                path_filename = os.path.basename(file_path_to_remove)
                path_removed = self.remove_document_by_filename(path_filename)
                if path_removed > 0:
                    logger.info(f"Successfully removed {path_removed} additional chunks by file path")
                    additional_removed += path_removed
            
            # Now check to ensure document is really gone
            remaining_chunks = 0
            for doc_key, doc in self.documents.items():
                metadata = doc.get('metadata', {})
                if metadata.get('document_id') == document_id:
                    remaining_chunks += 1
                    logger.warning(f"Document still has chunk in vector store by ID: {doc_key}")
                elif url_to_remove and 'url' in metadata and url_to_remove in metadata['url']:
                    remaining_chunks += 1
                    logger.warning(f"Document still has chunk in vector store by URL: {doc_key}")
                elif filename_to_remove and 'filename' in metadata and filename_to_remove in metadata['filename']:
                    remaining_chunks += 1
                    logger.warning(f"Document still has chunk in vector store by filename: {doc_key}")
                elif file_path_to_remove and 'file_path' in metadata and file_path_to_remove in metadata['file_path']:
                    remaining_chunks += 1
                    logger.warning(f"Document still has chunk in vector store by file_path: {doc_key}")
                
            if remaining_chunks > 0:
                logger.warning(f"Document {document_id} still has {remaining_chunks} chunks in vector store after removal!")
            else:
                logger.info(f"Document {document_id} completely removed from vector store")
                
            total_removed = removed_count + additional_removed
            logger.info(f"Removed total of {total_removed} chunks (initial: {removed_count}, additional: {additional_removed})")
            return total_removed
            
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
            
    @property
    def document_ids(self):
        """
        Get a list of all document IDs in the vector store.
        
        Returns:
            list: List of all document IDs
        """
        return list(self.documents.keys())
        
    # Alias for unload_from_memory for better compatibility
    def unload(self):
        """
        Alias for unload_from_memory() for better API compatibility.
        This implements maximum memory release by completely unloading the vector store.
        
        Returns:
            int: Number of documents unloaded
        """
        logger.debug("Using unload() alias for maximum memory release")
        return self.unload_from_memory()
