import os
import logging
import json
import time
import hashlib
from functools import lru_cache
from typing import Dict, Tuple, Any

# Handle numpy import with fallback for vector operations
try:
    import numpy as np
except ImportError:
    # Create a simple fallback for basic operations if numpy is not available
    class NumpyFallback:
        def array(self, data):
            return data
        def dot(self, a, b):
            # Simple dot product for lists
            return sum(x*y for x, y in zip(a, b))
    np = NumpyFallback()

from openai import OpenAI

# Import necessary functions for DOI extraction and citations
from utils.doi_lookup import get_metadata_from_doi, extract_doi_from_text, get_citation_from_doi, extract_and_get_citation

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize OpenAI client
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# Embedding cache with time-based expiration - optimized for memory efficiency
_embedding_cache: Dict[str, Tuple[np.ndarray, float]] = {}
_CACHE_TTL = 60 * 1  # 1 minute cache TTL in seconds (reduced from 2)
_MAX_CACHE_SIZE = 50  # Maximum number of embeddings to cache (reduced from 75)
_CACHE_CLEANUP_INTERVAL = 20  # Clean up every 20 seconds (reduced from 30)
_CACHE_MEMORY_LIMIT_MB = 10  # Maximum cache size in MB to prevent excessive memory usage

# Create a last cleanup tracker
_last_cache_cleanup_time = time.time()

def _compute_text_hash(text: str) -> str:
    """
    Compute a hash of the input text to use as a cache key.
    
    Args:
        text (str): The text to hash
        
    Returns:
        str: A hash string of the text
    """
    # Limit text length for hash computation
    if len(text) > 1000:
        text = text[:1000]  # Use only first 1000 chars for very long text
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def _cleanup_embedding_cache():
    """
    Clean up expired cache entries and enforce maximum cache size and memory limits.
    """
    global _last_cache_cleanup_time
    global _embedding_cache
    
    current_time = time.time()
    # Remove expired entries
    expired_keys = [
        key for key, (_, timestamp) in _embedding_cache.items()
        if current_time - timestamp > _CACHE_TTL
    ]
    
    for key in expired_keys:
        del _embedding_cache[key]
    
    # Calculate current cache memory usage
    cache_size_mb = sum(embedding.nbytes for embedding, _ in _embedding_cache.values()) / (1024 * 1024)
    
    # If cache exceeds memory limit or entry count limit, remove oldest entries
    if cache_size_mb > _CACHE_MEMORY_LIMIT_MB or len(_embedding_cache) > _MAX_CACHE_SIZE:
        # Sort by timestamp (oldest first)
        sorted_items = sorted(_embedding_cache.items(), key=lambda x: x[1][1])
        
        # Calculate how many entries to keep based on both constraints
        keep_count = _MAX_CACHE_SIZE
        
        if cache_size_mb > _CACHE_MEMORY_LIMIT_MB:
            # Start with an aggressive cut - keep only 50% of items if we exceed memory limit
            memory_based_keep_count = len(sorted_items) // 2
            keep_count = min(keep_count, memory_based_keep_count)
            
            # Ensure we keep at least some minimum number of entries
            keep_count = max(5, keep_count)
        
        # Keep only the newest entries
        _embedding_cache = dict(sorted_items[-keep_count:])
        
        # After cleanup, recalculate size for logging
        cache_size_mb = sum(embedding.nbytes for embedding, _ in _embedding_cache.values()) / (1024 * 1024)
    
    # Log cache size after cleanup
    logger.debug(f"Embedding cache cleanup: {len(_embedding_cache)} entries, {cache_size_mb:.2f}MB, memory limit: {_CACHE_MEMORY_LIMIT_MB}MB")

def clear_embedding_cache():
    """
    Clear the embedding cache entirely. Useful for reducing memory during deep sleep.
    
    Returns:
        int: Number of entries cleared
    """
    global _embedding_cache
    cache_size = len(_embedding_cache)
    _embedding_cache = {}
    logger.info(f"Embedding cache cleared: {cache_size} entries removed")
    return cache_size

def get_embedding(text):
    """
    Get embedding for text using OpenAI's API with optimized memory-efficient caching.
    
    Args:
        text (str): Text to embed
        
    Returns:
        numpy.ndarray: Embedding vector
    """
    global _last_cache_cleanup_time, _embedding_cache
    
    # Handle empty text case efficiently
    if not text:
        logger.warning("Empty text provided for embedding")
        return np.zeros(1536, dtype=np.float32)
    
    # Optimize text length - use more aggressive truncation to save memory
    # 8000 chars is the absolute max for the API, but we can use less for memory efficiency
    max_length = 4000  # Reduced from 8000 to save memory, sufficient for most documents
    if len(text) > max_length:
        logger.warning(f"Text too long for embedding ({len(text)} chars), truncating to {max_length}")
        text = text[:max_length]
    
    # Use more aggressive compression on text for hash computation
    text_hash = _compute_text_hash(text)
    
    # Memory check before cache lookup - if we're approaching memory limits,
    # proactively clean up cache
    # Calculate cache size in MB
    if len(_embedding_cache) > 10:  # Only check if we have a meaningful number of entries
        cache_size_mb = sum(embedding.nbytes for embedding, _ in _embedding_cache.values()) / (1024 * 1024)
        if cache_size_mb > _CACHE_MEMORY_LIMIT_MB * 0.8:  # If we're at 80% of limit
            logger.warning(f"Cache size {cache_size_mb:.2f}MB approaching limit of {_CACHE_MEMORY_LIMIT_MB}MB, cleaning up")
            _cleanup_embedding_cache()
            _last_cache_cleanup_time = time.time()
    
    # Check cache with improved handling
    if text_hash in _embedding_cache:
        embedding, timestamp = _embedding_cache[text_hash]
        current_time = time.time()
        
        # More frequent checks for cache cleanup with tighter constraints
        if (len(_embedding_cache) > _MAX_CACHE_SIZE * 0.8 or  # Lower threshold (80%)
            (current_time - timestamp > _CACHE_TTL * 0.5) or  # Half the TTL for aggressive cleanup
            (current_time - _last_cache_cleanup_time > _CACHE_CLEANUP_INTERVAL)):
            _cleanup_embedding_cache()
            _last_cache_cleanup_time = current_time
            
        # If still in cache after cleanup, return it
        if text_hash in _embedding_cache:
            return embedding
    
    # Not in cache, need to compute
    try:
        # Reuse client connection to avoid creating new connections
        response = client.embeddings.create(
            model="text-embedding-ada-002",
            input=text
        )
        
        # Use more memory-efficient storage by using float16 instead of float32 where possible
        # This cuts memory usage in half with minimal precision loss for similarity searches
        embedding = np.array(response.data[0].embedding, dtype=np.float16)
        
        # Cache with timestamp
        _embedding_cache[text_hash] = (embedding, time.time())
        
        # More aggressive cleanup trigger (at 80% capacity)
        if len(_embedding_cache) >= _MAX_CACHE_SIZE * 0.8:
            _cleanup_embedding_cache()
            _last_cache_cleanup_time = time.time()
        
        return embedding
    except Exception as e:
        logger.exception(f"Error getting embedding: {str(e)}")
        # Create an empty embedding with proper shape instead of random to save memory
        return np.zeros(1536, dtype=np.float16)

def generate_response(query, context_documents):
    """
    Generate response to a query using the OpenAI API.
    
    Args:
        query (str): User query
        context_documents (list): List of relevant documents for context
        
    Returns:
        tuple: (answer, sources)
    """
    try:
        # Prepare context from retrieved documents
        context = ""
        all_sources = []
        pdf_sources = {}  # Track PDF sources by title
        
        # Sort documents by relevance score (lower is better in FAISS)
        # This ensures the most relevant documents are included first
        sorted_docs = sorted(context_documents, key=lambda x: x.get('score', 1.0))
        
        # Limit to top 5 most relevant documents
        context_documents = sorted_docs[:5]
        
        # Create a document ID mapping to ensure consistency
        doc_id_mapping = {i+1: doc for i, doc in enumerate(context_documents)}
        
        # Track source types for debugging
        source_types = {}
        for doc in context_documents:
            source_type = doc["metadata"].get("source_type", "unknown")
            source_types[source_type] = source_types.get(source_type, 0) + 1
        
        logger.info(f"Query source types: {source_types}")
        
        # First pass: Create source info and track PDFs
        for i, doc in enumerate(context_documents):
            # Add document to context with citation marker
            context += f"\nDocument [{i+1}]:\n{doc['text']}\n"
            
            # Extract metadata for debugging
            metadata = doc["metadata"]
            
            # Log the full document metadata for debugging
            logger.info(f"Document {i+1} full metadata: {json.dumps(metadata, default=str)}")
            
            # Get source type or infer it from other metadata
            source_type = metadata.get("source_type", None)
            
            # If source_type is not explicitly set, try to infer it
            if not source_type:
                # Get document ID for inference
                doc_id_str = str(doc.get("id", ""))
                
                if metadata.get("file_type") == "pdf" or "pdf" in doc_id_str.lower() or metadata.get("document_title"):
                    source_type = "pdf"
                elif metadata.get("url"):
                    source_type = "website"
                else:
                    source_type = "unknown"
            
            # Log detailed source info for debugging
            if source_type == "website":
                logger.debug(f"Website source {i+1}: URL={metadata.get('url', 'unknown')}, Title={metadata.get('title', 'unknown')}")
            elif source_type == "pdf":
                logger.debug(f"PDF source {i+1}: Title={metadata.get('title', 'unknown')}, Page={metadata.get('page', 'unknown')}")
                # Add more detailed debugging for citation info
                logger.debug(f"PDF citation details: formatted_citation={metadata.get('formatted_citation', 'None')}, citation={metadata.get('citation', 'None')}, doi={metadata.get('doi', 'None')}")
            
            # Prepare source information for citation
            source_info = {
                "source_type": source_type,
                "content": doc["text"][:200] + ("..." if len(doc["text"]) > 200 else ""),
                "doc_id": i+1  # Keep track of the document ID in context
            }
            
            # Include citation if available
            if metadata.get("citation"):
                source_info["citation"] = metadata.get("citation")
                # Also set formatted_citation for consistency and to ensure it's available
                if not metadata.get("formatted_citation"):
                    source_info["formatted_citation"] = metadata.get("citation")
            
            # Handle different source types
            if source_type == "pdf":
                # Try different ways to get a meaningful title
                title = None
                
                # First try direct title
                if metadata.get("title") and metadata.get("title").strip():
                    title = metadata.get("title")
                    logger.debug(f"Using direct title: {title}")
                
                # If no title, try to extract from filename
                if not title and metadata.get("file_path"):
                    import os
                    filename = os.path.basename(metadata.get("file_path"))
                    # Remove timestamp pattern if present (like 20250328202349_)
                    if len(filename) > 15 and filename[:8].isdigit() and filename[8:15].isdigit() and filename[15] == '_':
                        filename = filename[16:]
                    
                    # Remove extension and format
                    file_title = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").title()
                    if file_title:
                        title = file_title
                        logger.debug(f"Using filename-derived title: {title}")
                
                # If no title from direct or filename, try to get first part of citation
                if not title and metadata.get("formatted_citation"):
                    # Extract the title part (usually before the first period)
                    citation_parts = metadata.get("formatted_citation").split(".", 1)
                    if len(citation_parts) > 0 and citation_parts[0].strip():
                        title = citation_parts[0].strip()
                        logger.debug(f"Using citation-derived title: {title}")
                
                # Last resort fallback
                if not title:
                    title = "Rheumatology Document"
                    logger.debug("Using fallback title: Rheumatology Document")
                
                page = metadata.get("page", "unknown")
                source_info["title"] = title
                source_info["page"] = page
                
                # Track PDFs by title
                if title in pdf_sources:
                    # Add this page to the existing PDF source
                    pdf_sources[title]["pages"].add(str(page))
                    # Add this document ID to the list of doc_ids
                    pdf_sources[title]["doc_ids"].append(i+1)
                    # We'll still add this to all_sources for context tracking
                else:
                    # Create a new PDF entry with a fallback citation if none exists
                    citation = source_info.get("citation", "")
                    
                    # Check for a citation in the metadata as well
                    if not citation or citation.strip() == "":
                        # PRIORITY CHANGE: Check formatted_citation FIRST as it's the most complete citation
                        if metadata.get("formatted_citation"):
                            citation = metadata.get("formatted_citation")
                            logger.debug(f"Using formatted_citation for PDF: {citation}")
                        # Then check for direct citation in metadata
                        elif metadata.get("citation"):
                            citation = metadata.get("citation")
                            logger.debug(f"Using citation for PDF: {citation}")
                        # Check for a DOI to use in the citation
                        elif metadata.get("doi"):
                            # Try to get a complete citation from the DOI using external service
                            success, doi_metadata = get_citation_from_doi(metadata.get("doi"))
                            if success and doi_metadata.get("formatted_citation"):
                                citation = doi_metadata.get("formatted_citation")
                                logger.debug(f"Using DOI lookup service citation for PDF: {citation}")
                            else:
                                citation = f"{title}. https://doi.org/{metadata.get('doi')}"
                                logger.debug(f"Using basic DOI-based citation for PDF: {citation}")
                        else:
                            # Try to extract a DOI directly from the text
                            text = doc.get("text", "")
                            if text:
                                success, extracted_metadata = extract_and_get_citation(text)
                                if success and extracted_metadata.get("formatted_citation"):
                                    citation = extracted_metadata.get("formatted_citation")
                                    logger.debug(f"Using text-extracted DOI citation for PDF: {citation}")
                                else:
                                    # Create a better fallback citation based on the title
                                    citation = f"{title}. (Rheumatology Document)"
                                    logger.debug(f"Using fallback citation for PDF: {citation}")
                            else:
                                # Create a better fallback citation based on the title
                                citation = f"{title}. (Rheumatology Document)"
                                logger.debug(f"Using fallback citation for PDF: {citation}")
                    
                    pdf_sources[title] = {
                        "title": title,
                        "citation": citation,
                        "source_type": "pdf",
                        "pages": {str(page)},
                        "doc_ids": [i+1]
                    }
            elif source_type == "website":
                title = metadata.get("title", "Unnamed Website")
                url = metadata.get("url", "#")
                page_number = metadata.get("page_number", None)
                source_info["title"] = title
                source_info["url"] = url
                
                # Include page number from multi-page crawl if available
                if page_number is not None:
                    source_info["page_number"] = page_number
                
                # Ensure website citations are properly formatted
                if "citation" not in source_info or not source_info["citation"]:
                    page_info = f" (Page {page_number})" if page_number is not None else ""
                    source_info["citation"] = f"Website: {title}{page_info} - {url}"
                
                logger.debug(f"Added website source {i+1} with citation: {source_info.get('citation', 'No citation')}")
            else:
                # For other source types, ensure we have fallbacks for all properties
                
                # Try to find a meaningful title from various metadata fields
                title = metadata.get("title", None)
                
                if not title and metadata.get("document_title"):
                    title = metadata.get("document_title")
                
                if not title and metadata.get("file_path"):
                    # Try to extract a better title from the file_path
                    file_path = metadata.get("file_path", "")
                    if file_path:
                        # Get the filename part
                        import os
                        filename = os.path.basename(file_path)
                        # Remove extension and format
                        title = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").title()
                
                source_info["title"] = title or "Rheumatology Document"
                source_info["url"] = metadata.get("url", "#")
                
                # If no citation exists, create one
                if "citation" not in source_info or not source_info["citation"]:
                    title = metadata.get("title", "Rheumatology Document")
                    url = metadata.get("url", None)
                    
                    # Format the filename to be more user-friendly
                    if title == "Rheumatology Document" and "file_path" in metadata:
                        # Try to extract a better title from the file_path
                        file_path = metadata.get("file_path", "")
                        if file_path:
                            # Get the filename part
                            import os
                            filename = os.path.basename(file_path)
                            # Remove extension and format
                            title = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").title()
                    
                    if url:
                        source_info["citation"] = f"{title}. Retrieved from {url}"
                    else:
                        # More descriptive citation when URL is not available
                        # PRIORITY CHANGE: Check formatted_citation FIRST as it's the most complete citation
                        if metadata.get("formatted_citation"):
                            source_info["citation"] = metadata.get("formatted_citation")
                            logger.debug(f"Using formatted_citation for other document: {source_info['citation']}")
                        # Then check for direct citation in metadata
                        elif metadata.get("citation"):
                            source_info["citation"] = metadata.get("citation")
                            logger.debug(f"Using citation for other document: {source_info['citation']}")
                        # Check for DOI to create a citation with DOI link
                        elif metadata.get("doi"):
                            # Try to get a complete citation from the DOI using external service
                            success, doi_metadata = get_citation_from_doi(metadata.get("doi"))
                            if success and doi_metadata.get("formatted_citation"):
                                source_info["citation"] = doi_metadata.get("formatted_citation")
                                logger.debug(f"Using DOI lookup service citation for other document: {source_info['citation']}")
                            else:
                                source_info["citation"] = f"{title}. https://doi.org/{metadata.get('doi')}"
                                logger.debug(f"Using basic DOI-based citation for other document: {source_info['citation']}")
                        else:
                            # Try to extract a DOI directly from the document text
                            text = doc.get("text", "")
                            if text:
                                success, extracted_metadata = extract_and_get_citation(text)
                                if success and extracted_metadata.get("formatted_citation"):
                                    source_info["citation"] = extracted_metadata.get("formatted_citation")
                                    logger.debug(f"Using text-extracted DOI citation for other document: {source_info['citation']}")
                                else:
                                    source_info["citation"] = f"{title}. (Document from Rheumatology Knowledge Base)"
                                    logger.debug(f"Using fallback citation for other document: {source_info['citation']}")
                            else:
                                source_info["citation"] = f"{title}. (Document from Rheumatology Knowledge Base)"
                                logger.debug(f"Using fallback citation for other document: {source_info['citation']}")
            
            all_sources.append(source_info)
            
        # Second pass: Create deduplicated sources for display
        sources = []
        
        # Create a mapping of document IDs to ensure all cited IDs have sources
        doc_id_to_source = {}
        
        # Log PDF sources for debugging
        logger.info(f"Processing {len(pdf_sources.keys())} PDF sources")
        
        # First add all deduplicated PDF sources
        for title, pdf_info in pdf_sources.items():
            # Skip sources with title "Health Canada Rheumatoid Arthritis Factsheet" as this was deleted
            # Also skip if the file_path contains "Health_Canada_rheumatoid-arthritis-factsheet"
            # Also skip if the citation mentions the Health Canada document
            if ("Health Canada Rheumatoid Arthritis Factsheet" in title or 
                (pdf_info.get("file_path") and "Health_Canada_rheumatoid-arthritis-factsheet" in pdf_info.get("file_path", "")) or
                (pdf_info.get("citation") and "Health Canada Rheumatoid Arthritis Factsheet" in pdf_info.get("citation", ""))):
                logger.info(f"Skipping deleted document: {title}")
                continue
                
            # Create a combined citation with page numbers
            pdf_source = {
                "source_type": "pdf",
                "title": title,
                "pages": sorted(pdf_info["pages"], key=lambda x: int(x) if x.isdigit() else 0),
                "doc_ids": pdf_info["doc_ids"]
            }
            
            # Register this source with all its document IDs
            for doc_id in pdf_info["doc_ids"]:
                doc_id_to_source[doc_id] = pdf_source
            
            # Include the citation if available
            if pdf_info["citation"]:
                pdf_source["citation"] = pdf_info["citation"]
                
            # Add page numbers to the citation
            page_str = ", ".join(pdf_source["pages"])
            if "citation" in pdf_source:
                # If citation exists, append page numbers to it
                if " (page " not in pdf_source["citation"]:
                    pdf_source["citation"] += f" (page{'' if len(pdf_source['pages']) == 1 else 's'} {page_str})"
            else:
                # Create a basic citation with page numbers
                pdf_source["citation"] = f"{title} (page{'' if len(pdf_source['pages']) == 1 else 's'} {page_str})"
                
            sources.append(pdf_source)
        
        # Then add all non-PDF sources
        website_sources = {}  # Track website sources by URL and page to handle multi-page crawls
        
        # First collect website sources with improved logging
        for source in all_sources:
            if source["source_type"] == "website":
                url = source.get("url", "#")
                page_number = source.get("page_number", None)
                
                # Create a unique key that combines URL and page number
                source_key = f"{url}#{page_number}" if page_number is not None else url
                
                if source_key not in website_sources:
                    website_sources[source_key] = source
                    logger.info(f"Adding website source to final results: {source.get('title', 'Website Source')} - {url}" + 
                               (f" (Page {page_number})" if page_number is not None else ""))
                    
                    # Log full source details for debugging
                    logger.debug(f"Website source details: {source}")
        
        # Add website sources to the final sources list with page numbers preserved
        for key, source in website_sources.items():
            # Make sure the website citation is properly formatted
            if "citation" not in source or not source["citation"]:
                title = source.get("title", "Website")
                url = source.get("url", "#")
                page_number = source.get("page_number", None)
                page_info = f" (Page {page_number})" if page_number is not None else ""
                source["citation"] = f"Website: {title}{page_info} - {url}"
                
            logger.info(f"Final website citation: {source['citation']}")
            sources.append(source)
            
        # Add any other non-PDF, non-website sources
        for source in all_sources:
            if source["source_type"] != "pdf" and source["source_type"] != "website":
                # Make sure we have a valid citation
                if "citation" not in source or not source["citation"]:
                    # Create a default citation if none exists
                    title = source.get("title", "Rheumatology Document")
                    url = source.get("url", None)
                    
                    # Try to extract a better title if we have a file_path
                    if title == "Rheumatology Document" and "file_path" in source:
                        # Try to extract a better title from the file_path
                        file_path = source.get("file_path", "")
                        if file_path:
                            # Get the filename part
                            import os
                            filename = os.path.basename(file_path)
                            # Remove extension and format
                            title = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").title()
                    
                    if url:
                        source["citation"] = f"{title}. Retrieved from {url}"
                    elif source.get("doi"):
                        # Try to get a complete citation from the DOI using external service
                        success, doi_metadata = get_citation_from_doi(source.get("doi"))
                        if success and doi_metadata.get("formatted_citation"):
                            source["citation"] = doi_metadata.get("formatted_citation")
                            logger.debug(f"Using DOI lookup service citation for final source: {source['citation']}")
                        else:
                            source["citation"] = f"{title}. https://doi.org/{source.get('doi')}"
                    else:
                        # Look for a properly formatted citation from our metadata before falling back
                        if "metadata" in source and source["metadata"] and "citation" in source["metadata"]:
                            source["citation"] = source["metadata"]["citation"]
                        elif "metadata" in source and source["metadata"] and "formatted_citation" in source["metadata"]:
                            source["citation"] = source["metadata"]["formatted_citation"]
                        else:
                            source["citation"] = f"{title}. (Document from Rheumatology Knowledge Base)"
                
                # Make sure we have required fields
                if "title" not in source or not source["title"]:
                    source["title"] = "Rheumatology Document"
                
                # Add the source
                sources.append(source)
        
        # Log the query and context for debugging
        logger.debug(f"Query: {query}")
        logger.debug(f"Context documents count: {len(context_documents)}")
        
        # Skip API call if there's no context
        if not context.strip():
            return "ROXI doesn't have enough information in the rheumatology knowledge base to answer this question based on the documents you've provided.", []
        
        # Create prompt for OpenAI with more explicit instructions
        # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
        # do not change this unless explicitly requested by the user
        
        # System prompt
        system_prompt = (
            "You are ROXI (Rheumatology Optimized eXpert Intelligence), a specialized assistant that answers questions about rheumatology based on the provided document context. "
            "When answering, follow these rules:\n"
            "1. CRITICAL: Even if the documents only partially or indirectly address the query, make your very best effort to extract and synthesize ANY relevant information.\n"
            "2. NEVER say 'ROXI doesn't have enough information' unless the documents are completely unrelated. If you see ANY potentially relevant terms or concepts in ANY document, use them to provide a partial answer.\n"
            "3. Be EXTREMELY generous in extracting relevant information - if website menus, navigation elements, or section titles contain relevant terms, use them as a basis for your answer.\n"
            "4. Many website sources may only contain brief references or category names - treat these as valuable and interpret them as indications that the website covers those topics.\n"
            "5. Provide citations for your answer using the format [n] where n is the document number.\n"
            "6. IMPORTANT: Cite multiple sources when the same information appears in multiple documents. Always include ALL relevant sources, not just the first one you find.\n"
            "7. IMPORTANT: Always make sure that every citation number [n] in your answer is included in the sources list.\n"
            "8. CRITICAL: When you use a citation like [3] or [4] in your answer, ensure that source #3 or #4 appears in your final sources list.\n"
            "9. DO NOT include a 'Sources:' section at the end of your answer - citations will be displayed separately in the interface.\n"
            "10. Be concise and direct in your answers.\n"
            "11. Pay equal attention to ALL document sources - both PDFs and websites. Some of your most valuable information may come from website sources.\n"
            "12. Website sources may include multiple pages from the same domain, each containing different information - treat each page as a distinct source of knowledge.\n"
            "13. If documents provide conflicting information, acknowledge this and present both viewpoints with citations.\n"
            "14. If you find information from websites, especially rheumatology-focused websites, treat this as high-quality information comparable to peer-reviewed sources.\n"
            "15. When citing website sources, include the specific page number if available, as this indicates which specific page from the domain was used.\n"
            "16. If the documents contain website navigation elements or section headers related to the query, interpret these as indications that the website contains content on those topics.\n"
            "17. For website content that appears to be chapter or section titles, extrapolate that the site likely contains detailed information on those topics even if not provided in the context.\n"
            "18. When discussing any rheumatology condition, include details on clinical phenotypes, organ involvement, diagnosis, and treatment approaches if found in the context.\n"
            "19. If you see even brief mentions of specific conditions in the context, prioritize these for a comprehensive answer.\n"
            
            "SPECIALIZED RHEUMATOLOGY GUIDELINES:\n"
            "20. You are a comprehensive rheumatology knowledge base covering ALL rheumatic conditions including:\n"
            "   - Inflammatory arthritides (RA, PsA, SpA, AS, etc.)\n"
            "   - Connective tissue diseases (SLE, SSc, myositis, Sjögren's, MCTD, etc.)\n"
            "   - Vasculitides (GCA, Takayasu's, ANCA-associated, IgG4-RD, etc.)\n"
            "   - Crystal arthropathies (gout, CPPD, BCP, etc.)\n"
            "   - Autoinflammatory syndromes (AOSD, FMF, CAPS, etc.)\n"
            "   - Other conditions (fibromyalgia, osteoarthritis, PMR, etc.)\n"
            
            "21. When encountering disease abbreviations or terms in context, recognize their significance:\n"
            "   - 'RA' → rheumatoid arthritis, 'PsA' → psoriatic arthritis, 'SpA' → spondyloarthritis\n"
            "   - 'AS' → ankylosing spondylitis, 'axSpA' → axial spondyloarthritis\n"
            "   - 'SLE' → systemic lupus erythematosus, 'SSc' → systemic sclerosis, 'MCTD' → mixed connective tissue disease\n"
            "   - 'GCA' → giant cell arteritis, 'PMR' → polymyalgia rheumatica\n"
            "   - 'ANCA' → anti-neutrophil cytoplasmic antibody, 'GPA' → granulomatosis with polyangiitis\n"
            "   - 'IgG4-RD' → IgG4-related disease\n"
            
            "22. Emphasize the multisystem nature and disease spectrum of rheumatic conditions, acknowledging that many have overlapping features\n"
            
            "23. Interpret website navigation sections about specific diseases as strong evidence that the site contains comprehensive information about these conditions"
        )
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": f"Question: {query}\n\nContext documents:\n{context}\n\nPlease answer the question based on the context. Make your best effort to provide useful information from these documents even if they only partially address the query."
                }
            ],
            temperature=0.3,
            max_tokens=1000
        )
        
        answer = response.choices[0].message.content
        logger.debug(f"Generated response for query: {query[:30]}...")
        
        # Check if the answer says there's not enough information
        if "I don't have enough information" in answer:
            # If the answer indicates no information but we have sources,
            # check if this is really the case or just a model hallucination
            if len(context_documents) >= 3:
                # If we have at least 3 documents, try one more time with stronger instruction
                # Base retry prompt
                retry_prompt = (
                    "You are ROXI (Rheumatology Optimized eXpert Intelligence), a specialized assistant that answers questions about rheumatology based on the provided document context. "
                    "CRITICAL INSTRUCTION: The user has provided documents that ABSOLUTELY DO contain information "
                    "related to their query. In this retry attempt, you MUST extract anything useful from the context to construct a helpful response. "
                    "DO NOT under any circumstances claim there's insufficient information.\n\n"
                    
                    "IMPORTANT GUIDELINES:\n"
                    "1. Even if you only see website menus, navigation elements, or section titles in the context, use these as STRONG EVIDENCE that the website "
                    "contains information on those topics. For example, if you see 'Spondyloarthropathies' in a menu, this is extremely valuable information.\n\n"
                    
                    "2. Interpret website navigation elements and categories as firm evidence that the site covers those topics in depth. A website section "
                    "titled 'Diseases including Axial Spondyloarthritis' is proof that the source contains information about spondyloarthritis.\n\n"
                    
                    "3. When extracting information from website sources, look for ANY terms related to the question and use those as a basis for your answer. "
                    "If you see a menu item or category that matches terms in the query, consider this relevant information.\n\n"
                    
                    "4. Provide citations for your answer using the format [n] where n is the document number.\n\n"
                    
                    "5. IMPORTANT: Always make sure that every citation number [n] in your answer is included in the sources list you provide at the end.\n\n"
                    
                    "6. CRITICAL: When you use a citation like [3] or [4] in your answer, ensure that source #3 or #4 appears in your final sources list.\n\n"
                    
                    "7. For questions about rheumatology conditions that appear as section titles or categories in website menus, provide a response that "
                    "acknowledges the website as a source covering that topic, even if specific details aren't in the context.\n\n"
                    
                    "8. For navigation links, titles, or category listings, extrapolate reasonably about what content would be found there based on "
                    "standard knowledge of rheumatology.\n\n"
                    
                    "Remember that website sources, especially specialized rheumatology websites, are extremely valuable resources "
                    "and you should prioritize extracting information from them, even if only category or section names are available."
                )
                
                # Enhance the retry prompt with specific emphasis on extracting disease information from website structures
                retry_prompt += (
                    "\n\nSPECIAL INSTRUCTION FOR RHEUMATOLOGY DISEASE QUERIES:\n"
                    "1. For any rheumatology condition mentioned in the query, it is GUARANTEED that the provided documents contain some form of related information.\n"
                    "2. Look especially carefully for ANY mentions of specific diseases or conditions in the context, even in navigation menus or section titles.\n"
                    "3. If you see any rheumatology condition mentioned ANYWHERE in the context, consider this highly relevant information.\n"
                    "4. If a rheumatology website has ANY mention of a specific condition in its structure, it should be interpreted as covering this topic in depth.\n"
                    "5. For disease-specific questions, look for clinical phenotypes, organ involvement patterns, diagnostic criteria, and treatment approaches.\n"
                    "6. Even passing mentions of autoimmune or inflammatory conditions should be included in your answer as they may be relevant.\n"
                    "7. CRITICAL: Websites that list specific rheumatology diseases as categories are specialty sources that absolutely have detailed information on those conditions.\n\n"
                    
                    "COMPREHENSIVE RHEUMATOLOGY KNOWLEDGE BASE:\n"
                    "You cover ALL rheumatic conditions including:\n"
                    "- Inflammatory arthritides (RA, PsA, SpA, AS, etc.)\n"
                    "- Connective tissue diseases (SLE, SSc, myositis, Sjögren's, MCTD, etc.)\n"
                    "- Vasculitides (GCA, Takayasu's, ANCA-associated, IgG4-RD, etc.)\n"
                    "- Crystal arthropathies (gout, CPPD, BCP, etc.)\n"
                    "- Autoinflammatory syndromes (AOSD, FMF, CAPS, etc.)\n"
                    "- Other conditions (fibromyalgia, osteoarthritis, PMR, etc.)\n\n"
                    
                    "When encountering disease abbreviations in context, recognize them:\n"
                    "- 'RA' → rheumatoid arthritis, 'PsA' → psoriatic arthritis, 'SpA' → spondyloarthritis\n"
                    "- 'AS' → ankylosing spondylitis, 'axSpA' → axial spondyloarthritis\n"
                    "- 'SLE' → systemic lupus erythematosus, 'SSc' → systemic sclerosis\n"
                    "- 'GCA' → giant cell arteritis, 'PMR' → polymyalgia rheumatica\n"
                    "- 'ANCA' → anti-neutrophil cytoplasmic antibody, 'GPA' → granulomatosis with polyangiitis\n"
                    "- 'IgG4-RD' → IgG4-related disease\n\n"
                    
                    "Emphasize the multisystem nature of rheumatic conditions, and acknowledge that many have overlapping features."
                )
                
                retry_response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "system",
                            "content": retry_prompt
                        },
                        {
                            "role": "user",
                            "content": f"Question: {query}\n\nContext documents:\n{context}"
                        }
                    ],
                    temperature=0.3,
                    max_tokens=1000
                )
                retry_answer = retry_response.choices[0].message.content
                
                # Only use the retry if it doesn't also claim insufficient information
                if "I don't have enough information" not in retry_answer:
                    answer = retry_answer
                    logger.debug("Used retry response as it provided better results")
                    
            # If the answer still indicates no information, don't return any sources
            if "I don't have enough information" in answer:
                return answer, []
        
        # Register website and other sources in the doc_id_mapping as well
        for source in all_sources:
            doc_id = source.get("doc_id")
            if doc_id and doc_id not in doc_id_to_source:
                # Deep copy to avoid modifying the original source
                source_copy = {k: v for k, v in source.items()}
                doc_id_to_source[doc_id] = source_copy
                logger.info(f"Registered source with ID {doc_id}: {source.get('title', 'Unknown')}")
        
        # Analyze the answer to find all citation references like [1], [2], etc.
        import re
        citation_refs = re.findall(r'\[(\d+)\]', answer)
        if citation_refs:
            citation_ids = set([int(ref) for ref in citation_refs])
            logger.info(f"Found citation references in answer: {citation_ids}")
            
            # CRITICAL CHANGE: Also check for source references in the "Source" section at the end
            source_section_match = re.search(r'Sources?:?\s*\n([\s\S]+)$', answer)
            if source_section_match:
                source_section = source_section_match.group(1)
                # Remove the source section from the answer as we'll handle citations properly
                answer = answer.replace(source_section_match.group(0), "")
                # Add our own sources section to the end
                answer = answer.strip() + "\n\nSources:"
            
            # Make sure all referenced documents appear in the final sources list
            final_sources = []
            doc_indices = {}  # Map to track document index in final sources list
            
            # Step 1: First collect all sources that are referenced in the text
            for doc_id in citation_ids:
                if doc_id in doc_id_to_source:
                    source = doc_id_to_source[doc_id]
                    
                    # Skip Health Canada document as requested - check both title and citation
                    if (("title" in source and "Health Canada Rheumatoid Arthritis Factsheet" in source.get("title", "")) or
                        ("citation" in source and "Health Canada Rheumatoid Arthritis Factsheet" in source.get("citation", "")) or
                        ("file_path" in source and "Health_Canada_rheumatoid-arthritis-factsheet" in source.get("file_path", ""))):
                        logger.info(f"Skipping deleted document reference: {source.get('title', '')}")
                        continue
                    
                    # Only add if not already included
                    source_title = source.get("title", "Unknown")
                    if all(s.get("title", "") != source_title for s in final_sources):
                        # Add source to list and track its position
                        final_sources.append(source)
                        doc_indices[doc_id] = len(final_sources)
                        logger.info(f"Added source for citation [{doc_id}] at position {len(final_sources)}: {source_title}")
                    else:
                        # Get the index of the existing source
                        for i, s in enumerate(final_sources):
                            if s.get("title", "") == source_title:
                                doc_indices[doc_id] = i + 1
                                logger.info(f"Document ID {doc_id} mapped to existing source at position {i+1}")
                                break
                else:
                    logger.warning(f"Citation reference [{doc_id}] has no corresponding source!")
                    
                    # Try to find the original document and create a basic source
                    if doc_id in doc_id_mapping:
                        orig_doc = doc_id_mapping[doc_id]
                        metadata = orig_doc.get("metadata", {})
                        
                        # Skip Health Canada document as requested - check both title and file path
                        if (("title" in metadata and "Health Canada Rheumatoid Arthritis Factsheet" in metadata.get("title", "")) or
                            ("file_path" in metadata and "Health_Canada_rheumatoid-arthritis-factsheet" in metadata.get("file_path", ""))):
                            logger.info(f"Skipping deleted document reference from metadata: {metadata.get('title', '')}")
                            continue
                            
                        # Look for a proper citation from various sources
                        citation = None
                        title = metadata.get("title", "Rheumatology Document")
                        
                        # Try to get the best possible citation
                        if metadata.get("formatted_citation"):
                            citation = metadata.get("formatted_citation")
                            logger.info(f"Using formatted_citation for document {doc_id}: {citation}")
                        elif metadata.get("citation"):
                            citation = metadata.get("citation")
                            logger.info(f"Using citation for document {doc_id}: {citation}")
                        elif metadata.get("doi"):
                            # Try to use DOI lookup to get a proper citation
                            # Import the DOI lookup function if needed
                            from utils.doi_lookup import get_metadata_from_doi
                            
                            # Try to get a citation from the DOI
                            logger.info(f"Trying DOI lookup for {metadata.get('doi')}")
                            try:
                                doi_metadata = get_metadata_from_doi(metadata.get('doi'))
                                if doi_metadata and "formatted_citation" in doi_metadata:
                                    citation = doi_metadata["formatted_citation"]
                                    logger.info(f"Got citation from DOI lookup: {citation}")
                                else:
                                    citation = f"{title}. https://doi.org/{metadata.get('doi')}"
                                    logger.info(f"Using basic DOI-based citation: {citation}")
                            except Exception as e:
                                logger.error(f"Error during DOI lookup: {str(e)}")
                                citation = f"{title}. https://doi.org/{metadata.get('doi')}"
                                logger.info(f"Using basic DOI-based citation after error: {citation}")
                        else:
                            # Try to extract DOI from the text - more aggressive approach
                            # Get text from the original document or any chunks we can find
                            text = ""
                            
                            # First try document text
                            if orig_doc.get("text"):
                                text = orig_doc.get("text", "")
                                
                            # If no text or too short, try to get text from all chunks with the same doc_id
                            if len(text) < 1000 and isinstance(doc_id_mapping, dict):
                                all_chunks_text = []
                                for doc_key, doc_value in doc_id_mapping.items():
                                    # If document belongs to same PDF based on filename pattern
                                    if doc_value.get("metadata") and doc_value.get("metadata").get("file_path") and metadata.get("file_path"):
                                        doc_filename = os.path.basename(doc_value.get("metadata").get("file_path", ""))
                                        current_filename = os.path.basename(metadata.get("file_path", ""))
                                        
                                        # Try to match filenames ignoring timestamp prefixes
                                        if len(doc_filename) > 15 and doc_filename[:8].isdigit() and doc_filename[8:15].isdigit() and doc_filename[15] == '_':
                                            doc_filename = doc_filename[16:]
                                        if len(current_filename) > 15 and current_filename[:8].isdigit() and current_filename[8:15].isdigit() and current_filename[15] == '_':
                                            current_filename = current_filename[16:]
                                            
                                        if doc_filename == current_filename:
                                            if doc_value.get("text"):
                                                all_chunks_text.append(doc_value.get("text", ""))
                                
                                # Combine all chunks text
                                if all_chunks_text:
                                    combined_text = "\n".join(all_chunks_text)
                                    # Use combined text if it's longer than the current text
                                    if len(combined_text) > len(text):
                                        text = combined_text
                                        logger.info(f"Using combined text from multiple chunks: {len(text)} characters")
                            
                            if text:
                                # Try to extract DOI
                                doi = extract_doi_from_text(text)
                                if doi:
                                    logger.info(f"Extracted DOI from text: {doi}")
                                    success, doi_metadata = get_citation_from_doi(doi)
                                    if success and doi_metadata and "formatted_citation" in doi_metadata:
                                        citation = doi_metadata["formatted_citation"]
                                        logger.info(f"Got citation from extracted DOI: {citation}")
                                    else:
                                        logger.info(f"DOI extraction succeeded but citation lookup failed")
                                        # Even if lookup failed, we can still use the DOI for a basic citation
                                        citation = f"{title}. https://doi.org/{doi}"
                                        logger.info(f"Using basic DOI-based citation: {citation}")
                                else:
                                    logger.info(f"Could not extract DOI from {len(text)} characters of text")
                            
                            # If we still don't have a citation, try to get a better title from filename
                            if not citation and metadata.get("file_path"):
                                import os
                                filename = os.path.basename(metadata.get("file_path", ""))
                                if filename:
                                    # Remove timestamp prefix if present
                                    if len(filename) > 15 and filename[:8].isdigit() and filename[8:15].isdigit() and filename[15] == '_':
                                        filename = filename[16:]
                                    title = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").title()
                            
                            # If we still don't have a citation, use a basic one
                            if not citation:
                                # Look for authors in metadata
                                authors = metadata.get("authors", "")
                                year = metadata.get("publication_year", "")
                                journal = metadata.get("journal", "")
                                
                                if authors and year and journal:
                                    citation = f"{authors}. ({year}). {title}. {journal}."
                                    logger.info(f"Created citation from metadata: {citation}")
                                else:
                                    citation = f"{title}. (Rheumatology Document)"
                                    logger.info(f"Using basic citation for document {doc_id}: {citation}")
                        
                        # Try to find this document in the database by file path if PDF
                        db_document = None
                        if metadata.get("source_type") == "pdf" and metadata.get("file_path"):
                            # Import models here to avoid circular imports
                            from app import app
                            from models import Document
                            
                            # Get the filename without timestamp prefix
                            import os
                            filename = os.path.basename(metadata.get("file_path", ""))
                            if filename:
                                # Remove timestamp prefix if present
                                if len(filename) > 15 and filename[:8].isdigit() and filename[8:15].isdigit() and filename[15] == '_':
                                    filename = filename[16:]
                                    
                                # Clean filename matches in database
                                try:
                                    with app.app_context():
                                        db_document = Document.query.filter(Document.filename.like(f'%{filename}')).first()
                                        if db_document:
                                            # Use the database document information for better citation
                                            logger.info(f"Found document in database: {db_document.title}")
                                            title = db_document.title or title
                                            if db_document.formatted_citation:
                                                citation = db_document.formatted_citation
                                                logger.info(f"Using database citation: {citation}")
                                except Exception as e:
                                    logger.error(f"Error looking up document in database: {str(e)}")
                            
                        # Create source with all available information
                        basic_source = {
                            "source_type": metadata.get("source_type", "unknown"),
                            "doc_id": doc_id,
                            "title": title,
                            "citation": citation
                        }
                        
                        # Add page information if available
                        if metadata.get("page"):
                            basic_source["pages"] = [str(metadata.get("page"))]
                            if "page" not in citation.lower():
                                basic_source["citation"] += f" (page {metadata.get('page')})"
                        
                        final_sources.append(basic_source)
                        # Track this source's position
                        doc_indices[doc_id] = len(final_sources)
                        logger.info(f"Created basic source for citation [{doc_id}] at position {len(final_sources)}: {basic_source.get('title', 'Unknown')}")
            
            # Step 2: Re-number citations in the answer text based on the final source list
            for doc_id in sorted(citation_ids, reverse=True):  # Process in reverse to avoid index conflicts
                if doc_id in doc_indices:
                    # Replace [doc_id] with the actual position in the sources list
                    actual_index = doc_indices[doc_id]
                    answer = answer.replace(f"[{doc_id}]", f"[{actual_index}]")
                    logger.info(f"Replaced citation [{doc_id}] with [{actual_index}]")
                else:
                    # If doc_id was filtered out (e.g., Health Canada document), replace with a generic citation
                    # rather than removing it completely, to preserve the text flow
                    if "Health_Canada" in str(doc_id) or "Health Canada" in str(doc_id):
                        # Only completely remove Health Canada references
                        answer = answer.replace(f"[{doc_id}]", "")
                        logger.info(f"Removed citation [{doc_id}] as it was a filtered Health Canada document")
                    else:
                        # Replace other filtered citations with reference to the first source
                        # This ensures citations don't disappear from the text
                        if len(final_sources) > 0:
                            answer = answer.replace(f"[{doc_id}]", f"[1]")
                            logger.info(f"Replaced filtered citation [{doc_id}] with [1]")
                        else:
                            # If there are no sources left at all, remove the citation
                            answer = answer.replace(f"[{doc_id}]", "")
                            logger.info(f"Removed citation [{doc_id}] as there are no valid sources")
            
            # Remove any "Sources:" section that might be in the answer body (added by the model)
            # This pattern matches "Sources:" followed by a list of numbered items
            sources_pattern = r'\*\*Sources:\*\*.*?\d+\.\s.*?(?=\n\n|$)'
            answer = re.sub(sources_pattern, '', answer, flags=re.DOTALL)
            
            # Also try to match other variations - including the "Sources:" at the end
            sources_pattern2 = r'Sources:.*?(\d+\.\s.*?)?(?=\n\n|$)'
            answer = re.sub(sources_pattern2, '', answer, flags=re.DOTALL)
            
            # Also catch any remaining trailing "Sources:" text
            answer = re.sub(r'\s*Sources:\s*$', '', answer, flags=re.DOTALL)
            
            # Clean up any double newlines that might result
            answer = re.sub(r'\n{3,}', '\n\n', answer)
            
            # Fix duplicate citations like [1][1] - replace with [1]
            duplicate_citation_pattern = r'\[(\d+)\]\[(\d+)\]'
            
            # Keep searching until no more duplicates are found
            while re.search(duplicate_citation_pattern, answer):
                match = re.search(duplicate_citation_pattern, answer)
                if match:
                    # If the citation numbers are the same, replace with just one citation
                    if match.group(1) == match.group(2):
                        answer = re.sub(r'\[' + match.group(1) + r'\]\[' + match.group(2) + r'\]', 
                                        f'[{match.group(1)}]', answer, 1)
                    else:
                        # If they're different, keep both but separate them with a space
                        answer = re.sub(r'\[' + match.group(1) + r'\]\[' + match.group(2) + r'\]', 
                                        f'[{match.group(1)}] [{match.group(2)}]', answer, 1)
            
            # Return only the sources that were actually referenced
            return answer, final_sources
            
        # If no citations were found or something went wrong, return all sources
        return answer, sources
    except Exception as e:
        logger.exception(f"Error generating response: {str(e)}")
        return f"ROXI encountered an error while analyzing your question: {str(e)}", []
