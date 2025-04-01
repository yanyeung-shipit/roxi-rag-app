import fitz  # PyMuPDF
import os
import logging
from utils.citation_manager import extract_citation_info
from utils.text_splitter import chunk_text

logger = logging.getLogger(__name__)

def process_pdf_generator(file_path, file_name):
    """
    Generator-based memory-efficient PDF parser.
    Yields one chunk at a time with shared metadata.
    """
    logger.info(f"Memory-efficient processing of {file_path}")

    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if file_size_mb > 50:
        raise Exception(f"PDF too large: {file_size_mb:.2f} MB (limit 50MB)")

    doc = fitz.open(file_path)
    num_pages = len(doc)
    logger.debug(f"PDF has {num_pages} pages")

    metadata = {
        'file_size': int(file_size_mb * 1024 * 1024),
        'page_count': num_pages,
        'doi': None,
        'authors': None,
        'journal': None,
        'publication_year': None,
        'volume': None,
        'issue': None,
        'pages': None,
        'formatted_citation': None,
        'title': file_name
    }

    # Extract citation
    formatted_citation, citation_metadata = extract_citation_info(file_name, file_path)
    metadata['formatted_citation'] = formatted_citation
    if citation_metadata:
        metadata.update({
            'doi': citation_metadata.get('DOI'),
            'volume': citation_metadata.get('volume'),
            'issue': citation_metadata.get('issue'),
            'pages': citation_metadata.get('page'),
            'journal': citation_metadata.get('container-title', [None])[0] if isinstance(citation_metadata.get('container-title'), list) else citation_metadata.get('container-title')
        })

        # Format authors
        if 'author' in citation_metadata:
            authors = []
            for a in citation_metadata['author']:
                if 'family' in a:
                    authors.append(f"{a['family']}, {a.get('given', '')}".strip())
            metadata['authors'] = "; ".join(authors)

        if 'published' in citation_metadata and 'date-parts' in citation_metadata['published']:
            parts = citation_metadata['published']['date-parts']
            if parts and parts[0]:
                metadata['publication_year'] = parts[0][0]

    max_pages = min(num_pages, 50)
    max_chunks = 200
    chunk_count = 0

    for page_num in range(max_pages):
        try:
            page = doc[page_num]
            text = page.get_text("text")

            if text:
                if len(text) > 10000:
                    text = text[:10000] + "..."

                chunks = chunk_text(text, max_length=1500, overlap=150)
                for i, chunk in enumerate(chunks):
                    if chunk_count >= max_chunks:
                        logger.warning("Max chunks reached (200)")
                        return

                    chunk_metadata = {
                        **metadata,
                        "page": page_num + 1,
                        "chunk_index": i,
                        "citation": metadata["formatted_citation"]
                    }

                    yield {
                        "text": chunk,
                        "metadata": chunk_metadata
                    }, metadata

                    chunk_count += 1
        except Exception as e:
            logger.warning(f"Page {page_num + 1} failed: {e}")
            continue

    doc.close()
