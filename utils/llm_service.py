import os
import logging
import json
import numpy as np
from openai import OpenAI

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
        
        # First pass: Create source info and track PDFs
        for i, doc in enumerate(context_documents):
            # Add document to context with citation marker
            context += f"\nDocument [{i+1}]:\n{doc['text']}\n"
            
            # Prepare source information for citation
            source_info = {
                "source_type": doc["metadata"].get("source_type", "unknown"),
                "content": doc["text"][:200] + ("..." if len(doc["text"]) > 200 else ""),
                "doc_id": i+1  # Keep track of the document ID in context
            }
            
            # Include citation if available
            if doc["metadata"].get("citation"):
                source_info["citation"] = doc["metadata"].get("citation")
            
            # Handle different source types
            if doc["metadata"].get("source_type") == "pdf":
                title = doc["metadata"].get("title", "Unnamed PDF")
                page = doc["metadata"].get("page", "unknown")
                source_info["title"] = title
                source_info["page"] = page
                
                # Track PDFs by title
                if title in pdf_sources:
                    # Add this page to the existing PDF source
                    pdf_sources[title]["pages"].add(str(page))
                    # We'll still add this to all_sources for context tracking
                else:
                    # Create a new PDF entry
                    pdf_sources[title] = {
                        "title": title,
                        "citation": source_info.get("citation", ""),
                        "source_type": "pdf",
                        "pages": {str(page)},
                        "doc_ids": [i+1]
                    }
            else:
                source_info["title"] = doc["metadata"].get("title", "Unnamed Source")
                source_info["url"] = doc["metadata"].get("url", "#")
            
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
        for source in all_sources:
            if source["source_type"] != "pdf":
                sources.append(source)
        
        # Log the query and context for debugging
        logger.debug(f"Query: {query}")
        logger.debug(f"Context documents count: {len(context_documents)}")
        
        # Skip API call if there's no context
        if not context.strip():
            return "I don't have enough information to answer this question based on the documents you've provided.", []
        
        # Create prompt for OpenAI with more explicit instructions
        # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
        # do not change this unless explicitly requested by the user
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful assistant that answers questions based on the provided document context. "
                        "When answering, follow these rules:\n"
                        "1. IMPORTANT: Try your best to answer the question using the provided documents, even if they only partially address the query.\n"
                        "2. Only say 'I don't have enough information to answer this question' if the documents are completely unrelated or irrelevant.\n"
                        "3. Be generous in extracting relevant information - if documents contain anything potentially useful, use it.\n"
                        "4. Provide citations for your answer using the format [n] where n is the document number.\n"
                        "5. Cite multiple sources if the information comes from multiple documents.\n"
                        "6. Be concise and direct in your answers.\n"
                        "7. If documents provide conflicting information, acknowledge this and present both viewpoints with citations."
                    )
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
                retry_response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a helpful assistant that answers questions based on the provided document context. "
                                "IMPORTANT INSTRUCTION: The user has provided documents that DO contain relevant information "
                                "for their query. Your task is to extract useful information from these documents to answer "
                                "the question, even if the information is partial or incomplete. Do NOT claim there is insufficient "
                                "information unless you're absolutely certain after careful consideration."
                            )
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
        return f"I'm sorry, but I encountered an error while generating a response: {str(e)}", []
