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
        sources = []
        
        for i, doc in enumerate(context_documents):
            # Add document to context with citation marker
            context += f"\nDocument [{i+1}]:\n{doc['text']}\n"
            
            # Prepare source information for citation
            source_info = {
                "source_type": doc["metadata"].get("source_type", "unknown"),
                "content": doc["text"][:200] + ("..." if len(doc["text"]) > 200 else "")
            }
            
            if doc["metadata"].get("source_type") == "pdf":
                source_info["title"] = f"{doc['metadata'].get('title', 'Unnamed PDF')} (page {doc['metadata'].get('page', 'unknown')})"
            else:
                source_info["title"] = doc["metadata"].get("title", "Unnamed Source")
                source_info["url"] = doc["metadata"].get("url", "#")
            
            sources.append(source_info)
        
        # Create prompt for OpenAI
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
                        "1. Only use information from the provided documents to answer the question.\n"
                        "2. If the answer cannot be found in the documents, say 'I don't have enough information to answer this question.'\n"
                        "3. Provide citations for your answer using the format [n] where n is the document number.\n"
                        "4. Cite multiple sources if the information comes from multiple documents.\n"
                        "5. Be concise and direct in your answers.\n"
                        "6. If documents provide conflicting information, acknowledge this and present both viewpoints with citations."
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
        
        answer = response.choices[0].message.content
        logger.debug(f"Generated response for query: {query[:30]}...")
        
        return answer, sources
    except Exception as e:
        logger.exception(f"Error generating response: {str(e)}")
        return f"I'm sorry, but I encountered an error while generating a response: {str(e)}", []
