"""
OpenAI service for generating embeddings and text.
"""
import os
import time
import logging
from typing import List, Dict, Any, Optional
import openai
from openai import OpenAI
import numpy as np

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# The embedding model to use
EMBEDDING_MODEL = "text-embedding-ada-002"

# GPT model to use (GPT-4 with vision capabilities)
# the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
# do not change this unless explicitly requested by the user
GPT_MODEL = "gpt-4o"

def get_openai_embedding(text: str, model: str = EMBEDDING_MODEL) -> List[float]:
    """
    Get an embedding from OpenAI for a single text.
    
    Args:
        text (str): The text to embed
        model (str): The embedding model to use
        
    Returns:
        List[float]: The embedding vector
    """
    # Handle empty or None text
    if not text or text.strip() == "":
        return np.zeros(1536).tolist()  # Return zeros vector of standard dimension
    
    try:
        # Truncate text if too long (max 8191 tokens for text-embedding-ada-002)
        # Approximate - each token is ~4 chars, with max 8191 tokens
        max_tokens = 8191
        max_chars = max_tokens * 4
        if len(text) > max_chars:
            logger.warning(f"Text too long ({len(text)} chars), truncating to {max_chars} chars")
            text = text[:max_chars]
        
        # Get embedding from OpenAI
        response = client.embeddings.create(
            model=model,
            input=text
        )
        
        embedding = response.data[0].embedding
        
        return embedding
    except Exception as e:
        logger.error(f"Error getting OpenAI embedding: {e}")
        # Return zeros vector as fallback (1536 is the standard dimension for text-embedding-ada-002)
        return np.zeros(1536).tolist()

def get_openai_embeddings_batch(texts: List[str], model: str = EMBEDDING_MODEL) -> List[List[float]]:
    """
    Get embeddings from OpenAI for multiple texts in a single request.
    
    Args:
        texts (List[str]): The texts to embed
        model (str): The embedding model to use
        
    Returns:
        List[List[float]]: The embedding vectors
    """
    # Handle empty list
    if not texts:
        return []
    
    # Process texts to handle empty or None entries and truncate if too long
    processed_texts = []
    for text in texts:
        # Handle empty or None text
        if not text or text.strip() == "":
            processed_texts.append("")
            continue
            
        # Truncate text if too long (max 8191 tokens for text-embedding-ada-002)
        # Approximate - each token is ~4 chars, with max 8191 tokens
        max_tokens = 8191
        max_chars = max_tokens * 4
        if len(text) > max_chars:
            logger.warning(f"Text too long ({len(text)} chars), truncating to {max_chars} chars")
            text = text[:max_chars]
            
        processed_texts.append(text)
    
    try:
        # Get embeddings from OpenAI
        response = client.embeddings.create(
            model=model,
            input=processed_texts
        )
        
        # Extract embeddings in the same order as input texts
        embeddings = [data.embedding for data in response.data]
        
        # Replace any empty text embeddings with zeros
        zeros_vector = np.zeros(1536).tolist()
        for i, text in enumerate(processed_texts):
            if not text:
                embeddings[i] = zeros_vector
        
        return embeddings
    except Exception as e:
        logger.error(f"Error getting batch OpenAI embeddings: {e}")
        # Return zeros vectors as fallback
        return [np.zeros(1536).tolist() for _ in texts]