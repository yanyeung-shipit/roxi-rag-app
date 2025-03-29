#!/usr/bin/env python
"""
Simple utility to get the next N chunks to process.
This is optimized for speed and simplicity.
"""

import os
import sys
import argparse
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

def get_next_chunks(last_processed_id, limit=5):
    """
    Get the next chunks to process after the given ID.
    
    Args:
        last_processed_id: The last processed chunk ID
        limit: Maximum number of chunks to return
        
    Returns:
        List of chunk IDs
    """
    # Connect to the database
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print("ERROR: DATABASE_URL environment variable not set", file=sys.stderr)
        return []
    
    try:
        # Create a database connection
        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Query for unprocessed chunks
        query = text("""
            SELECT id FROM document_chunks 
            WHERE id > :last_id
            ORDER BY id
            LIMIT :limit
        """)
        result = session.execute(query, {"last_id": last_processed_id, "limit": limit})
        
        # Convert to list
        chunk_ids = [row[0] for row in result]
        
        session.close()
        return chunk_ids
    
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return []

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Get the next chunks to process")
    parser.add_argument(
        "last_id",
        type=int,
        help="The last processed chunk ID"
    )
    parser.add_argument(
        "-l", "--limit",
        type=int,
        default=5,
        help="Maximum number of chunks to return"
    )
    
    args = parser.parse_args()
    
    chunk_ids = get_next_chunks(args.last_id, args.limit)
    for chunk_id in chunk_ids:
        print(chunk_id)

if __name__ == "__main__":
    main()