#!/usr/bin/env python
"""
Script to check the progress of the vector store rebuilding process.
This script provides a detailed report of the current status.
"""

import os
import json
import pickle
import psycopg2
from psycopg2.extras import RealDictCursor

# Constants
DB_URL = os.environ.get("DATABASE_URL")
VECTOR_DATA_FILE = "document_data.pkl"
CHECKPOINT_FILE = "processor_checkpoint.json"

def get_checkpoint_progress():
    """Get progress from the checkpoint file."""
    if not os.path.exists(CHECKPOINT_FILE):
        return None
    
    try:
        with open(CHECKPOINT_FILE, 'r') as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"Error reading checkpoint: {e}")
        return None

def get_vector_store_stats():
    """Get stats from the vector store."""
    if not os.path.exists(VECTOR_DATA_FILE):
        return None
    
    try:
        with open(VECTOR_DATA_FILE, 'rb') as f:
            document_data = pickle.load(f)
        
        processed_ids = set()
        for doc_id, doc in document_data.get("documents", {}).items():
            if "chunk_id" in doc:
                processed_ids.add(doc["chunk_id"])
            elif "metadata" in doc and "chunk_id" in doc["metadata"]:
                processed_ids.add(doc["metadata"]["chunk_id"])
        
        return {
            "documents_count": len(document_data.get("documents", {})),
            "processed_chunks": len(processed_ids),
            "processed_ids": list(processed_ids)
        }
    except Exception as e:
        print(f"Error getting vector store stats: {e}")
        return None

def get_database_stats():
    """Get stats from the database."""
    try:
        conn = psycopg2.connect(DB_URL)
        stats = {}
        
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get total chunks
            cur.execute("SELECT COUNT(*) as total_chunks FROM document_chunks")
            stats.update(cur.fetchone())
            
            # Get total documents
            cur.execute("SELECT COUNT(*) as total_documents FROM documents")
            stats.update(cur.fetchone())
            
            # Get document details (top 5)
            cur.execute("""
                SELECT id, title, source_url, file_size,
                       created_at, updated_at 
                FROM documents
                ORDER BY created_at DESC
                LIMIT 5
            """)
            stats["recent_documents"] = cur.fetchall()
            
            # Get chunk info for document types
            cur.execute("""
                SELECT d.file_type, COUNT(c.id) as chunk_count
                FROM document_chunks c
                JOIN documents d ON c.document_id = d.id
                GROUP BY d.file_type
            """)
            stats["chunks_by_source_type"] = cur.fetchall()
        
        conn.close()
        return stats
    except Exception as e:
        print(f"Error getting database stats: {e}")
        return None

def get_running_process():
    """Check if processor is running."""
    try:
        if os.path.exists("processor.pid"):
            with open("processor.pid", 'r') as f:
                pid = f.read().strip()
            
            # Check if process is running
            if os.system(f"ps -p {pid} > /dev/null") == 0:
                return {"pid": pid, "running": True}
            else:
                return {"pid": pid, "running": False}
        return None
    except Exception as e:
        print(f"Error checking process: {e}")
        return None

def print_progress_report():
    """Print a comprehensive progress report."""
    checkpoint = get_checkpoint_progress()
    vector_stats = get_vector_store_stats()
    db_stats = get_database_stats()
    process = get_running_process()
    
    print("=" * 50)
    print("VECTOR STORE REBUILDING PROGRESS REPORT")
    print("=" * 50)
    
    # Process status
    if process:
        print(f"\nPROCESS STATUS: {'RUNNING' if process['running'] else 'STOPPED'}")
        print(f"Process ID: {process['pid']}")
    else:
        print("\nPROCESS STATUS: NO PROCESS FOUND")
    
    # Checkpoint data
    if checkpoint:
        print("\nCHECKPOINT DATA:")
        print(f"Last processed: Chunk {checkpoint.get('last_chunk_id')}")
        print(f"Last update: {checkpoint.get('timestamp')}")
        
        progress = checkpoint.get('progress', {})
        if progress:
            processed = progress.get('processed', 0)
            total = progress.get('total', 0)
            percentage = progress.get('percentage', 0)
            print(f"Progress: {processed}/{total} chunks ({percentage:.2f}%)")
    else:
        print("\nCHECKPOINT DATA: No checkpoint found")
    
    # Vector store stats
    if vector_stats:
        print("\nVECTOR STORE STATS:")
        print(f"Documents in vector store: {vector_stats['documents_count']}")
        print(f"Unique chunks processed: {vector_stats['processed_chunks']}")
    else:
        print("\nVECTOR STORE STATS: No vector store found")
    
    # Database stats
    if db_stats:
        print("\nDATABASE STATS:")
        print(f"Total documents: {db_stats['total_documents']}")
        print(f"Total chunks: {db_stats['total_chunks']}")
        
        if 'chunks_by_source_type' in db_stats:
            print("\nChunks by source type:")
            for entry in db_stats['chunks_by_source_type']:
                print(f"  {entry['file_type']}: {entry['chunk_count']} chunks")
        
        if vector_stats and db_stats['total_chunks'] > 0:
            percentage = (vector_stats['processed_chunks'] / db_stats['total_chunks']) * 100
            print(f"\nOVERALL PROGRESS: {vector_stats['processed_chunks']}/{db_stats['total_chunks']} chunks ({percentage:.2f}%)")
            
            if percentage < 40:
                chunks_remaining = int(0.4 * db_stats['total_chunks']) - vector_stats['processed_chunks']
                print(f"Chunks remaining to reach 40%: {chunks_remaining}")
                print(f"Estimated time at 3s per chunk: {(chunks_remaining * 3) / 60:.1f} minutes")
    else:
        print("\nDATABASE STATS: Could not connect to database")
    
    print("\n" + "=" * 50)

if __name__ == "__main__":
    print_progress_report()