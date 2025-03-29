import os
import logging
import json
import numpy as np
from openai import OpenAI

from utils.doi_lookup import get_citation_from_doi, extract_doi_from_text, extract_and_get_citation

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize OpenAI client
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

def get_embedding(text):
    """
    Get embedding for text using OpenAI's API.
    
    Args:
        text (str): Text to embed
        
    Returns:
        numpy.ndarray: Embedding vector
    """
    try:
        response = client.embeddings.create(
            model="text-embedding-ada-002",
            input=text
        )
        embedding = response.data[0].embedding
        return np.array(embedding, dtype=np.float32)
    except Exception as e:
        logger.exception(f"Error getting embedding: {str(e)}")
        # Fallback to random embedding for testing purposes only
        return np.random.rand(1536).astype(np.float32)

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
        
        # First add all deduplicated PDF sources
        for title, pdf_info in pdf_sources.items():
            # Create a combined citation with page numbers
            pdf_source = {
                "source_type": "pdf",
                "title": title,
                "pages": sorted(pdf_info["pages"], key=lambda x: int(x) if x.isdigit() else 0),
                "doc_ids": pdf_info["doc_ids"]
            }
            
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
            "6. Cite multiple sources if the information comes from multiple documents.\n"
            "7. IMPORTANT: Always make sure that every citation number [n] in your answer is included in the sources list you provide at the end.\n"
            "8. CRITICAL: When you use a citation like [3] or [4] in your answer, ensure that source #3 or #4 appears in your final sources list.\n"
            "9. Be concise and direct in your answers.\n"
            "10. Pay equal attention to ALL document sources - both PDFs and websites. Some of your most valuable information may come from website sources.\n"
            "11. Website sources may include multiple pages from the same domain, each containing different information - treat each page as a distinct source of knowledge.\n"
            "12. If documents provide conflicting information, acknowledge this and present both viewpoints with citations.\n"
            "13. If you find information from websites, especially rheumatology-focused websites, treat this as high-quality information comparable to peer-reviewed sources.\n"
            "14. When citing website sources, include the specific page number if available, as this indicates which specific page from the domain was used.\n"
            "15. If the documents contain website navigation elements or section headers related to the query, interpret these as indications that the website contains content on those topics.\n"
            "16. For website content that appears to be chapter or section titles, extrapolate that the site likely contains detailed information on those topics even if not provided in the context.\n"
            "17. When discussing any rheumatology condition, include details on clinical phenotypes, organ involvement, diagnosis, and treatment approaches if found in the context.\n"
            "18. If you see even brief mentions of specific conditions in the context, prioritize these for a comprehensive answer.\n"
            
            "SPECIALIZED RHEUMATOLOGY GUIDELINES:\n"
            "17. You are a comprehensive rheumatology knowledge base covering ALL rheumatic conditions including:\n"
            "   - Inflammatory arthritides (RA, PsA, SpA, AS, etc.)\n"
            "   - Connective tissue diseases (SLE, SSc, myositis, Sjögren's, MCTD, etc.)\n"
            "   - Vasculitides (GCA, Takayasu's, ANCA-associated, IgG4-RD, etc.)\n"
            "   - Crystal arthropathies (gout, CPPD, BCP, etc.)\n"
            "   - Autoinflammatory syndromes (AOSD, FMF, CAPS, etc.)\n"
            "   - Other conditions (fibromyalgia, osteoarthritis, PMR, etc.)\n"
            
            "18. When encountering disease abbreviations or terms in context, recognize their significance:\n"
            "   - 'RA' → rheumatoid arthritis, 'PsA' → psoriatic arthritis, 'SpA' → spondyloarthritis\n"
            "   - 'AS' → ankylosing spondylitis, 'axSpA' → axial spondyloarthritis\n"
            "   - 'SLE' → systemic lupus erythematosus, 'SSc' → systemic sclerosis, 'MCTD' → mixed connective tissue disease\n"
            "   - 'GCA' → giant cell arteritis, 'PMR' → polymyalgia rheumatica\n"
            "   - 'ANCA' → anti-neutrophil cytoplasmic antibody, 'GPA' → granulomatosis with polyangiitis\n"
            "   - 'IgG4-RD' → IgG4-related disease\n"
            
            "19. Emphasize the multisystem nature and disease spectrum of rheumatic conditions, acknowledging that many have overlapping features\n"
            
            "20. Interpret website navigation sections about specific diseases as strong evidence that the site contains comprehensive information about these conditions"
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
        
        return answer, sources
    except Exception as e:
        logger.exception(f"Error generating response: {str(e)}")
        return f"ROXI encountered an error while analyzing your question: {str(e)}", []
