import os
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship

db = SQLAlchemy()

class Document(db.Model):
    """Model for storing document metadata"""
    __tablename__ = 'documents'
    
    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=False)
    title = Column(String(255))
    file_type = Column(String(50), nullable=False)  # "pdf", "website", etc.
    source_url = Column(Text, nullable=True)  # For website documents
    file_path = Column(String(255), nullable=True)  # For local files
    file_size = Column(Integer, nullable=True)  # In bytes
    page_count = Column(Integer, nullable=True)  # For PDFs
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    processed = Column(Boolean, default=False)
    
    # One document has many chunks
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    # One document can be in many collections (through collection_documents)
    collections = relationship("Collection", secondary="collection_documents", back_populates="documents")
    
    def __repr__(self):
        return f"<Document {self.filename}>"


class DocumentChunk(db.Model):
    """Model for storing document chunks with their vector embeddings"""
    __tablename__ = 'document_chunks'
    
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey('documents.id'), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    page_number = Column(Integer, nullable=True)  # For PDFs
    text_content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Many chunks belong to one document
    document = relationship("Document", back_populates="chunks")
    
    def __repr__(self):
        return f"<DocumentChunk {self.id} from document {self.document_id}>"


class Collection(db.Model):
    """Model for organizing documents into collections"""
    __tablename__ = 'collections'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Many collections have many documents (through collection_documents)
    documents = relationship("Document", secondary="collection_documents", back_populates="collections")
    
    def __repr__(self):
        return f"<Collection {self.name}>"


# Association table for many-to-many relationship between collections and documents
collection_documents = db.Table(
    'collection_documents',
    Column('collection_id', Integer, ForeignKey('collections.id'), primary_key=True),
    Column('document_id', Integer, ForeignKey('documents.id'), primary_key=True)
)