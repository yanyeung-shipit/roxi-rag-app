#!/usr/bin/env python
"""
Script to check the progress of the vector store rebuilding process.
This script provides a detailed report of the current status.
It supports both the 50% and 65% processor services.
"""

import os
import json
import pickle
import argparse
import psycopg2
from datetime import datetime
from psycopg2.extras import RealDictCursor

# Constants
DB_URL = os.environ.get("DATABASE_URL")
VECTOR_DATA_FILE = "document_data.pkl"
CHECKPOINT_FILES = [
    "processor_checkpoint.json",           # 50% processor
    "process_to_65_percent_checkpoint.json", # 65% processor
    "enhanced_batch_checkpoint.json"        # Enhanced batch processor
]
PID_FILES = [
    "processor.pid",               # 50% processor
    "process_to_65_percent.pid",   # 65% processor
    "enhanced_rebuild.pid",         # Enhanced batch processor
    "fast_processor.pid"           # Fast processor 
]
TARGET_PERCENTAGE = 66.0

def get_checkpoint_progress():
    """Get progress from the checkpoint files, checking multiple options."""
    # Try each checkpoint file in order until we find one
    for checkpoint_file in CHECKPOINT_FILES:
        if os.path.exists(checkpoint_file):
            try:
                with open(checkpoint_file, 'r') as f:
                    data = json.load(f)
                return {
                    "file": checkpoint_file,
                    "data": data
                }
            except Exception as e:
                print(f"Error reading checkpoint {checkpoint_file}: {e}")
    
    # No valid checkpoint found
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
    """Check if any processor is running. Returns the first running process found."""
    try:
        for pid_file in PID_FILES:
            if os.path.exists(pid_file):
                with open(pid_file, 'r') as f:
                    pid = f.read().strip()
                
                # Check if process is running
                if os.system(f"ps -p {pid} > /dev/null") == 0:
                    return {
                        "pid": pid,
                        "running": True,
                        "pid_file": pid_file,
                        "processor_type": get_processor_type_from_pid_file(pid_file)
                    }
                else:
                    # Process not running but PID file exists
                    return {
                        "pid": pid,
                        "running": False,
                        "pid_file": pid_file,
                        "processor_type": get_processor_type_from_pid_file(pid_file)
                    }
        
        # No PID files found
        return None
    except Exception as e:
        print(f"Error checking process: {e}")
        return None

def get_processor_type_from_pid_file(pid_file):
    """Determine the processor type from the PID file name."""
    if "65_percent" in pid_file:
        return "65% Processor"
    elif "enhanced" in pid_file:
        return "Enhanced Processor"
    elif "fast" in pid_file:
        return "Fast Processor"
    else:
        return "50% Processor" # Default

def print_progress_report():
    """Print a comprehensive progress report."""
    checkpoint_info = get_checkpoint_progress()
    vector_stats = get_vector_store_stats()
    db_stats = get_database_stats()
    process = get_running_process()
    
    print("=" * 60)
    print("VECTOR STORE REBUILDING PROGRESS REPORT")
    print("=" * 60)
    
    # Process status
    if process:
        print(f"\nPROCESS STATUS: {'RUNNING' if process['running'] else 'STOPPED'}")
        print(f"Processor Type: {process['processor_type']}")
        print(f"Process ID: {process['pid']}")
        print(f"PID File: {process['pid_file']}")
    else:
        print("\nPROCESS STATUS: NO PROCESSOR RUNNING")
    
    # Checkpoint data
    if checkpoint_info:
        checkpoint_file = checkpoint_info.get('file')
        checkpoint = checkpoint_info.get('data', {})
        
        print(f"\nCHECKPOINT DATA ({checkpoint_file}):")
        
        # Different checkpoint files have different structures
        if "last_chunk_id" in checkpoint:
            # Old style checkpoint
            print(f"Last processed: Chunk {checkpoint.get('last_chunk_id')}")
            print(f"Last update: {checkpoint.get('timestamp')}")
            
            progress = checkpoint.get('progress', {})
            if progress:
                processed = progress.get('processed', 0)
                total = progress.get('total', 0)
                percentage = progress.get('percentage', 0)
                print(f"Progress: {processed}/{total} chunks ({percentage:.2f}%)")
        elif "processed_chunks" in checkpoint:
            # New style progress data
            processed = checkpoint.get('processed_chunks', 0)
            total = checkpoint.get('total_chunks', 0)
            percentage = checkpoint.get('percentage', 0)
            timestamp = checkpoint.get('timestamp', 'unknown')
            print(f"Progress: {processed}/{total} chunks ({percentage:.2f}%)")
            print(f"Last update: {timestamp}")
        elif "data" in checkpoint and isinstance(checkpoint["data"], dict):
            # Enhanced batch style
            data = checkpoint["data"]
            processed = data.get('processed_count', 0)
            total = data.get('total_count', 0)
            if total > 0:
                percentage = (processed / total) * 100
            else:
                percentage = 0
            print(f"Progress: {processed}/{total} chunks ({percentage:.2f}%)")
            print(f"Last update: {checkpoint.get('timestamp', 'unknown')}")
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
            processed_chunks = vector_stats['processed_chunks']
            total_chunks = db_stats['total_chunks']
            percentage = (processed_chunks / total_chunks) * 100
            print(f"\nOVERALL PROGRESS: {processed_chunks}/{total_chunks} chunks ({percentage:.2f}%)")
            
            # Calculate remaining to target
            if percentage < TARGET_PERCENTAGE:
                chunks_remaining = int((TARGET_PERCENTAGE / 100) * total_chunks) - processed_chunks
                print(f"Chunks remaining to reach {TARGET_PERCENTAGE}%: {chunks_remaining}")
                avg_time_per_chunk = 3  # seconds - could be adjusted based on historical data
                estimated_time = (chunks_remaining * avg_time_per_chunk) / 60  # minutes
                print(f"Estimated time remaining: {estimated_time:.1f} minutes")
    else:
        print("\nDATABASE STATS: Could not connect to database")
    
    print("\n" + "=" * 60)

def get_progress_data():
    """Get all progress data as a structured dictionary for JSON output."""
    checkpoint_info = get_checkpoint_progress()
    vector_stats = get_vector_store_stats()
    db_stats = get_database_stats()
    process = get_running_process()
    
    # Calculate overall stats
    overall_stats = {}
    if vector_stats and db_stats and 'total_chunks' in db_stats and db_stats['total_chunks'] > 0:
        processed_chunks = vector_stats['processed_chunks']
        total_chunks = db_stats['total_chunks']
        percentage = round((processed_chunks / total_chunks) * 100, 2)
        overall_stats = {
            "processed_chunks": processed_chunks,
            "total_chunks": total_chunks,
            "percentage": percentage,
            "target_percentage": TARGET_PERCENTAGE,
            "target_reached": percentage >= TARGET_PERCENTAGE,
            "timestamp": datetime.now().isoformat()
        }
        
        # Add remaining info
        if percentage < TARGET_PERCENTAGE:
            chunks_remaining = int((TARGET_PERCENTAGE / 100) * total_chunks) - processed_chunks
            avg_time_per_chunk = 3  # seconds
            estimated_time = round((chunks_remaining * avg_time_per_chunk) / 60, 1)  # minutes
            overall_stats.update({
                "chunks_remaining": chunks_remaining,
                "estimated_minutes_remaining": estimated_time
            })
    
    return {
        "process": process,
        "checkpoint": checkpoint_info,
        "vector_store": vector_stats,
        "database": db_stats,
        "overall": overall_stats
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check progress of vector store rebuilding")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument("--target", type=float, default=TARGET_PERCENTAGE, 
                       help=f"Target percentage to reach (default: {TARGET_PERCENTAGE}%)")
    args = parser.parse_args()
    
    # Update target if specified
    if args.target and args.target != TARGET_PERCENTAGE:
        TARGET_PERCENTAGE = args.target
    
    if args.json:
        import json
        # Get the progress data and print as JSON
        progress_data = get_progress_data()
        print(json.dumps(progress_data, default=str, indent=2))
    else:
        # Print human-readable report
        print_progress_report()