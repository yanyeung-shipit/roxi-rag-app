"""
Check database statistics to understand chunk processing status.
"""

import logging
from app import app
from models import db, Document, DocumentChunk

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_database_stats():
    """Get database statistics about documents and chunks."""
    with app.app_context():
        # Documents
        total_documents = Document.query.count()
        logger.info(f"Documents in DB: {total_documents}")
        
        # Document types
        pdf_documents = Document.query.filter_by(file_type='pdf').count()
        web_documents = Document.query.filter_by(file_type='website').count()
        other_documents = total_documents - pdf_documents - web_documents
        logger.info(f"PDF documents: {pdf_documents}")
        logger.info(f"Web documents: {web_documents}")
        logger.info(f"Other documents: {other_documents}")
        
        # Chunks
        total_chunks = DocumentChunk.query.count()
        logger.info(f"Total chunks: {total_chunks}")
        
        # Since the DocumentChunk model doesn't have a 'processed' field,
        # we'll count chunks that are in the vector store vs. total chunks
        chunk_ids_in_vector = set()
        try:
            # Import only here to avoid circular imports
            from utils.vector_store import VectorStore
            vector_store = VectorStore()
            # Get processed chunk IDs
            chunk_ids_in_vector = vector_store.get_processed_chunk_ids()
            logger.info(f"Chunks in vector store: {len(chunk_ids_in_vector)}")
            logger.info(f"Processing rate: {len(chunk_ids_in_vector)/total_chunks*100:.2f}%")
        except Exception as e:
            logger.error(f"Error getting vector store data: {e}")
        
        # Chunks per document
        chunks_per_document = {}
        for doc in Document.query.all():
            chunk_count = DocumentChunk.query.filter_by(document_id=doc.id).count()
            chunks_per_document[doc.id] = chunk_count
        
        # Top documents by chunk count
        top_documents = sorted(chunks_per_document.items(), key=lambda x: x[1], reverse=True)[:10]
        logger.info("\nTop 10 documents by chunk count:")
        for doc_id, chunk_count in top_documents:
            doc = Document.query.get(doc_id)
            title = doc.title if doc.title else "[No title]"
            shortened_title = title[:30] + "..." if len(title) > 30 else title
            logger.info(f"  Document {doc_id} ({shortened_title}): {chunk_count} chunks")
        
        # Documents without chunks
        docs_without_chunks = [doc_id for doc_id, count in chunks_per_document.items() if count == 0]
        logger.info(f"\nDocuments without chunks: {len(docs_without_chunks)}")
        
        # Sample documents without chunks
        if docs_without_chunks:
            sample_count = min(5, len(docs_without_chunks))
            logger.info(f"Sample of {sample_count} documents without chunks:")
            for i, doc_id in enumerate(docs_without_chunks[:sample_count]):
                doc = Document.query.get(doc_id)
                title = doc.title if doc.title else "[No title]"
                logger.info(f"  Document {doc_id}: {title} ({doc.file_type})")

if __name__ == "__main__":
    check_database_stats()