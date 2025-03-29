"""
Simple script to clear the vector store and database.
This ensures we have a clean state before uploading real documents.
"""
import os
import sys
from app import app, db, Document, DocumentChunk, Collection
from utils.vector_store import VectorStore

def clear_system():
    """
    Completely clear the vector store and all database records.
    This is a clean slate for the system.
    """
    print("Starting system cleanup...")
    
    # Initialize vector store
    vector_store = VectorStore()
    
    # First clear the vector store
    print("Clearing vector store...")
    vector_store.clear()
    
    # Then clear the database
    with app.app_context():
        try:
            print("Clearing database records...")
            # Start a transaction for all database operations
            # We need to delete in the correct order to respect foreign key constraints
            
            # First, clear collection_documents junction table
            db.session.execute(db.text("DELETE FROM collection_documents"))
            
            # Delete all document chunks first (due to foreign key constraint)
            chunk_count = DocumentChunk.query.count()
            DocumentChunk.query.delete()
            
            # Delete all documents
            doc_count = Document.query.count()
            Document.query.delete()
            
            # Delete all collections
            coll_count = Collection.query.count()
            Collection.query.delete()
            
            # Commit all changes
            db.session.commit()
            print(f"Successfully cleared database: {doc_count} documents, {chunk_count} chunks, {coll_count} collections")
        except Exception as db_error:
            # Rollback transaction on error
            db.session.rollback()
            print(f"Error clearing database: {str(db_error)}")
            raise
    
    print("System cleanup complete! Ready for new documents.")

if __name__ == "__main__":
    clear_system()