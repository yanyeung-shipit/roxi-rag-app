"""
Monitor Rebuild Progress

This script provides a user-friendly way to monitor the progress of vector store rebuilding.
It continuously displays progress information and updates at regular intervals.

Usage:
    python monitor_rebuild_progress.py [--interval SECONDS]
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, Any

import sqlalchemy as sa

from app import db
import models
from utils.vector_store import VectorStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
DEFAULT_INTERVAL = 10  # seconds

def get_progress_info() -> Dict[str, Any]:
    """
    Get comprehensive progress information from both the database and vector store.
    
    Returns:
        dict: Progress information with various metrics
    """
    # Initialize vector store to get processed chunks
    vector_store = VectorStore()
    processed_chunks = vector_store.get_processed_chunk_ids()
    num_processed = len(processed_chunks)
    
    # Get database statistics
    with db.engine.connect() as conn:
        # Get total document count
        total_docs = conn.execute(sa.text("SELECT COUNT(*) FROM document")).scalar()
        
        # Get total chunk count
        total_chunks = conn.execute(sa.text("SELECT COUNT(*) FROM document_chunk")).scalar()
        
        # Get document types
        doc_types = conn.execute(sa.text(
            "SELECT document_type, COUNT(*) FROM document GROUP BY document_type"
        )).fetchall()
        
        # Get top 5 documents by chunk count
        top_docs = conn.execute(sa.text("""
            SELECT d.id, d.title, COUNT(dc.id) as chunk_count
            FROM document d
            JOIN document_chunk dc ON d.id = dc.document_id
            GROUP BY d.id, d.title
            ORDER BY chunk_count DESC
            LIMIT 5
        """)).fetchall()
        
        # Get chunks per document average
        avg_chunks = conn.execute(sa.text("""
            SELECT AVG(chunk_count) FROM (
                SELECT COUNT(dc.id) as chunk_count
                FROM document d
                JOIN document_chunk dc ON d.id = dc.document_id
                GROUP BY d.id
            ) as chunks_per_doc
        """)).scalar()
    
    # Calculate progress
    progress_percentage = (num_processed / total_chunks * 100) if total_chunks > 0 else 0
    remaining_chunks = total_chunks - num_processed
    
    # Calculate time estimates
    # Assuming 3 seconds per chunk on average
    seconds_per_chunk = 3
    est_seconds_remaining = remaining_chunks * seconds_per_chunk
    est_completion = datetime.now() + timedelta(seconds=est_seconds_remaining)
    
    # Format document types
    doc_type_stats = {doc_type: count for doc_type, count in doc_types}
    
    # Format top documents
    top_doc_stats = [
        {"id": doc_id, "title": title, "chunk_count": chunk_count}
        for doc_id, title, chunk_count in top_docs
    ]
    
    return {
        "timestamp": datetime.now().isoformat(),
        "vector_store": {
            "processed_chunks": num_processed,
            "document_count": vector_store.get_stats().get("total_documents", 0)
        },
        "database": {
            "total_documents": total_docs,
            "total_chunks": total_chunks,
            "avg_chunks_per_document": round(avg_chunks, 1) if avg_chunks else 0,
            "document_types": doc_type_stats
        },
        "progress": {
            "percentage": progress_percentage,
            "processed": num_processed,
            "total": total_chunks,
            "remaining": remaining_chunks,
            "est_seconds_remaining": est_seconds_remaining,
            "est_completion": est_completion.isoformat()
        },
        "top_documents": top_doc_stats
    }

def format_time_remaining(seconds: int) -> str:
    """Format seconds into a human-readable time string."""
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if hours > 0:
        return f"{int(hours)}h {int(minutes)}m"
    elif minutes > 0:
        return f"{int(minutes)}m {int(seconds)}s"
    else:
        return f"{int(seconds)}s"

def display_progress(progress_info: Dict[str, Any], clear_screen: bool = True) -> None:
    """
    Display progress information in a user-friendly format.
    
    Args:
        progress_info: Progress information dictionary
        clear_screen: Whether to clear the screen before displaying
    """
    if clear_screen:
        os.system('clear' if os.name == 'posix' else 'cls')
    
    # Get progress data
    progress = progress_info["progress"]
    vector_store = progress_info["vector_store"]
    database = progress_info["database"]
    
    # Format timestamp
    timestamp = datetime.fromisoformat(progress_info["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
    
    # Format estimated completion time
    est_completion = datetime.fromisoformat(progress["est_completion"]).strftime("%Y-%m-%d %H:%M:%S")
    
    # Display header
    print("\n" + "=" * 70)
    print(f"  VECTOR STORE REBUILD PROGRESS - {timestamp}")
    print("=" * 70)
    
    # Display progress bar
    progress_bar_length = 50
    filled_length = int(progress_bar_length * progress["percentage"] / 100)
    bar = '█' * filled_length + '░' * (progress_bar_length - filled_length)
    print(f"\nProgress: [{bar}] {progress['percentage']:.1f}%")
    
    # Display progress details
    print(f"\nProcessed: {progress['processed']} / {progress['total']} chunks")
    print(f"Remaining: {progress['remaining']} chunks")
    print(f"Time left: {format_time_remaining(progress['est_seconds_remaining'])}")
    print(f"Est. completion: {est_completion}")
    
    # Display vector store details
    print("\n" + "-" * 70)
    print("VECTOR STORE STATS")
    print(f"Processed chunks: {vector_store['processed_chunks']}")
    print(f"Documents in vector store: {vector_store['document_count']}")
    
    # Display database details
    print("\n" + "-" * 70)
    print("DATABASE STATS")
    print(f"Total documents: {database['total_documents']}")
    print(f"Total chunks: {database['total_chunks']}")
    print(f"Avg. chunks per document: {database['avg_chunks_per_document']}")
    
    # Display document types
    print("\nDocument types:")
    for doc_type, count in database.get("document_types", {}).items():
        print(f"  - {doc_type}: {count}")
    
    # Display top documents
    print("\n" + "-" * 70)
    print("TOP DOCUMENTS BY CHUNK COUNT")
    for i, doc in enumerate(progress_info.get("top_documents", []), 1):
        print(f"{i}. Document {doc['id']}: {doc['title']} ({doc['chunk_count']} chunks)")
    
    print("\n" + "=" * 70)
    print(f"  Press Ctrl+C to exit")
    print("=" * 70 + "\n")

def monitor_progress(interval: int = DEFAULT_INTERVAL, json_output: bool = False) -> None:
    """
    Continuously monitor and display progress.
    
    Args:
        interval: Seconds between progress updates
        json_output: Whether to output JSON instead of formatted text
    """
    try:
        while True:
            # Get progress information
            progress_info = get_progress_info()
            
            if json_output:
                # Output as JSON
                print(json.dumps(progress_info, indent=2))
            else:
                # Display formatted progress
                display_progress(progress_info)
            
            # Wait for next update
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user.")

def main():
    """Main function to parse arguments and start monitoring."""
    parser = argparse.ArgumentParser(description='Monitor vector store rebuild progress')
    parser.add_argument('--interval', type=int, default=DEFAULT_INTERVAL,
                       help=f'Update interval in seconds (default: {DEFAULT_INTERVAL})')
    parser.add_argument('--json', action='store_true',
                       help='Output progress as JSON instead of formatted text')
    args = parser.parse_args()
    
    logger.info(f"Starting progress monitor with {args.interval}s interval")
    monitor_progress(args.interval, args.json)

if __name__ == '__main__':
    main()