import sys
import traceback

try:
    # Import necessary modules from process_to_65_percent_service.py
    import argparse
    import logging
    import os
    import pickle
    import time
    from datetime import datetime
    from typing import Dict, List, Any, Set, Union, Tuple

    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("Debug65PercentService")
    
    logger.info("Imports completed successfully")
    
    # Try to import database-related modules
    try:
        import sqlalchemy
        from sqlalchemy import create_engine, text
        logger.info("SQLAlchemy imported successfully")
    except Exception as e:
        logger.error(f"Failed to import SQLAlchemy: {e}")
        raise
    
    # Try to import vector store module
    try:
        from utils.vector_store import VectorStore
        logger.info("VectorStore imported successfully")
    except Exception as e:
        logger.error(f"Failed to import VectorStore: {e}")
        raise
    
    # Try to get database connection
    try:
        engine = create_engine(os.environ.get("DATABASE_URL"))
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            for row in result:
                logger.info(f"Database connection test: {row[0]}")
        logger.info("Database connection successful")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise
    
    # Try to get vector store
    try:
        vector_store = VectorStore()
        processed_ids = vector_store.get_processed_chunk_ids()
        logger.info(f"Vector store loaded successfully. {len(processed_ids)} chunks processed.")
    except Exception as e:
        logger.error(f"Failed to load vector store: {e}")
        raise
        
    # Try to import the main module
    try:
        from process_to_65_percent_service import main, Process65PercentService
        logger.info("Successfully imported the main module")
        
        # Try to initialize the service
        service = Process65PercentService(batch_size=5, target_percentage=65.0)
        logger.info("Successfully created service instance")
        
        # Try to get progress
        progress = service.get_progress()
        logger.info(f"Progress: {progress}")
        
        # Try to get next chunk batch
        chunks = service.get_next_chunk_batch()
        logger.info(f"Got {len(chunks)} chunks for next batch")
        
        if chunks:
            # Try to process first chunk
            logger.info(f"First chunk ID: {chunks[0]['id']}")
            success = service.process_chunk(chunks[0])
            logger.info(f"First chunk processing result: {success}")
        
    except Exception as e:
        logger.error(f"Failed in service execution: {e}")
        raise
        
    logger.info("Debug script completed successfully")
    
except Exception as e:
    logger.error(f"ERROR: {str(e)}")
    logger.error(f"TRACEBACK:\n{traceback.format_exc()}")
    print(f"Process crashed: {str(e)}")
    with open('processor_detailed_error.log', 'w') as f:
        f.write(f"ERROR: {str(e)}\n")
        f.write(f"TRACEBACK:\n{traceback.format_exc()}")
    sys.exit(1)
