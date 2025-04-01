"""Utility for splitting text into overlapping chunks for embeddings."""

def chunk_text(text, max_length=1500, overlap=150):
    """
    Split a long string into overlapping chunks of text.

    Each chunk will have up to `max_length` characters. Consecutive chunks overlap
    by `overlap` characters to preserve context between chunks (useful for embeddings).
    For example, with max_length=1500 and overlap=150, the first chunk is the first 
    1500 characters, and the next chunk starts 150 characters before the end of the first.

    Args:
        text (str): The input text to split.
        max_length (int): Maximum number of characters in each chunk.
        overlap (int): Number of characters to overlap between consecutive chunks.

    Returns:
        list[str]: A list of text chunks.
    """
    if overlap >= max_length:
        raise ValueError("overlap must be smaller than max_length to avoid infinite loop.")
    # If the text is short enough, no need to split.
    if len(text) <= max_length:
        return [text]

    chunks = []
    chunk_size = max_length  # for clarity in usage
    start = 0
    text_length = len(text)
    while start < text_length:
        end = min(text_length, start + chunk_size)
        chunk = text[start:end]
        chunks.append(chunk)
        if end == text_length:
            break  # reached the end of the text
        # Set the start for the next chunk `overlap` characters before the current chunk ends.
        start = end - overlap
    return chunks
