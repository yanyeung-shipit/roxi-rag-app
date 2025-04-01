# utils/text_splitter.py

def chunk_text(text, max_length=1500, overlap=150):
    """
    Splits text into overlapping chunks of approximately `max_length`, with `overlap` characters between chunks.
    """
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_length, len(text))
        chunks.append(text[start:end])
        start += max_length - overlap
    return chunks
