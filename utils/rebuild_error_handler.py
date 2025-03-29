"""
Error handling utilities for the vector store rebuild process.
This module provides functions to handle errors during the rebuild process
without halting the entire process.
"""
import os
import json
import time
import logging
import traceback
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# File paths for logs
ERROR_LOG_DIR = "logs/errors"
ERROR_LOG_PATH = f"{ERROR_LOG_DIR}/rebuild_errors.log"
RETRYABLE_DOCUMENTS_PATH = f"{ERROR_LOG_DIR}/retryable_documents.json"

# Error statistics
ERROR_STATS = {
    "total_errors": 0,
    "by_type": {},
    "by_document": {},
    "retried_documents": set(),
    "failed_documents": set(),
    "unrecoverable_errors": 0,
    "recoverable_errors": 0
}

def setup_error_directory():
    """Create the error directory structure if it doesn't exist."""
    if not os.path.exists(ERROR_LOG_DIR):
        os.makedirs(ERROR_LOG_DIR, exist_ok=True)
        logger.info(f"Created error log directory: {ERROR_LOG_DIR}")

def log_error(error_type: str, message: str, document_id: Optional[int] = None, 
              exception: Optional[Exception] = None, recoverable: bool = True) -> Dict[str, Any]:
    """
    Log an error to the error log file.
    
    Args:
        error_type (str): Type of error
        message (str): Error message
        document_id (int, optional): ID of the document related to the error
        exception (Exception, optional): Exception object
        recoverable (bool): Whether the error is recoverable
        
    Returns:
        dict: Error entry
    """
    setup_error_directory()
    
    # Get traceback if exception is provided
    tb = None
    if exception:
        tb = traceback.format_exc()
    
    # Create error entry
    error_entry = {
        "timestamp": datetime.now().isoformat(),
        "error_type": error_type,
        "message": message,
        "document_id": document_id,
        "traceback": tb,
        "recoverable": recoverable
    }
    
    # Update error statistics
    ERROR_STATS["total_errors"] += 1
    
    if error_type not in ERROR_STATS["by_type"]:
        ERROR_STATS["by_type"][error_type] = 0
    ERROR_STATS["by_type"][error_type] += 1
    
    if document_id is not None:
        doc_id_str = str(document_id)
        if doc_id_str not in ERROR_STATS["by_document"]:
            ERROR_STATS["by_document"][doc_id_str] = 0
        ERROR_STATS["by_document"][doc_id_str] += 1
        
        # Add to appropriate sets
        if recoverable:
            ERROR_STATS["recoverable_errors"] += 1
            # Add to retryable documents, but only if not already failed
            if doc_id_str not in ERROR_STATS["failed_documents"]:
                ERROR_STATS["retried_documents"].add(doc_id_str)
        else:
            ERROR_STATS["unrecoverable_errors"] += 1
            # If unrecoverable, mark as failed and remove from retryable
            ERROR_STATS["failed_documents"].add(doc_id_str)
            if doc_id_str in ERROR_STATS["retried_documents"]:
                ERROR_STATS["retried_documents"].remove(doc_id_str)
    
    # Write to the error log file
    with open(ERROR_LOG_PATH, "a") as f:
        f.write(json.dumps(error_entry) + "\n")
    
    # Update retryable documents file
    update_retryable_documents()
    
    # Log to the console
    if document_id is not None:
        logger.error(f"REBUILD ERROR: {error_type} - Document {document_id} - {message}")
    else:
        logger.error(f"REBUILD ERROR: {error_type} - {message}")
        
    if exception:
        logger.debug(f"Exception details: {tb}")
    
    return error_entry

def update_retryable_documents():
    """Update the retryable documents file with current retryable documents."""
    setup_error_directory()
    
    retryable = [int(doc_id) for doc_id in ERROR_STATS["retried_documents"]]
    failed = [int(doc_id) for doc_id in ERROR_STATS["failed_documents"]]
    
    retryable_data = {
        "timestamp": datetime.now().isoformat(),
        "retryable_documents": retryable,
        "failed_documents": failed,
        "stats": {
            "total_errors": ERROR_STATS["total_errors"],
            "recoverable_errors": ERROR_STATS["recoverable_errors"],
            "unrecoverable_errors": ERROR_STATS["unrecoverable_errors"]
        }
    }
    
    with open(RETRYABLE_DOCUMENTS_PATH, "w") as f:
        json.dump(retryable_data, f, indent=2)

def get_retryable_documents() -> List[int]:
    """
    Get the list of document IDs that had recoverable errors and can be retried.
    
    Returns:
        list: List of document IDs that can be retried
    """
    try:
        with open(RETRYABLE_DOCUMENTS_PATH, "r") as f:
            data = json.load(f)
            return data.get("retryable_documents", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return [int(doc_id) for doc_id in ERROR_STATS["retried_documents"]]

def retry_handler(func):
    """
    Decorator to handle retries for a function.
    
    Args:
        func: Function to decorate
        
    Returns:
        Decorated function
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        max_retries = kwargs.pop('max_retries', 3)
        retry_delay = kwargs.pop('retry_delay', 2)
        document_id = kwargs.get('document_id')
        
        # If document_id is not in kwargs, try to find it in args
        if document_id is None and args:
            # Check first arg if it's a document object
            if hasattr(args[0], 'id'):
                document_id = args[0].id
            # Otherwise check if first arg is an integer (likely a document ID)
            elif isinstance(args[0], int):
                document_id = args[0]
        
        retries = 0
        last_exception = None
        
        while retries <= max_retries:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                retries += 1
                
                # Log the error
                if retries <= max_retries:
                    log_error(
                        error_type="retry_error",
                        message=f"Error in {func.__name__}, retry {retries}/{max_retries}: {str(e)}",
                        document_id=document_id,
                        exception=e,
                        recoverable=True
                    )
                    
                    # Wait before retrying
                    time.sleep(retry_delay)
                else:
                    # Final failure
                    log_error(
                        error_type="max_retries_exceeded",
                        message=f"Maximum retries ({max_retries}) exceeded in {func.__name__}: {str(e)}",
                        document_id=document_id,
                        exception=e,
                        recoverable=False
                    )
                    
                    # Re-raise if requested
                    if kwargs.get('raise_on_max_retries', False):
                        raise
                    
                    # Otherwise return failure indicator
                    return None
        
        return None
    
    return wrapper

def safe_executor(func):
    """
    Decorator to safely execute a function and handle any exceptions.
    
    Args:
        func: Function to decorate
        
    Returns:
        Decorated function
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        document_id = kwargs.get('document_id')
        
        # If document_id is not in kwargs, try to find it in args
        if document_id is None and args:
            # Check first arg if it's a document object
            if hasattr(args[0], 'id'):
                document_id = args[0].id
            # Otherwise check if first arg is an integer (likely a document ID)
            elif isinstance(args[0], int):
                document_id = args[0]
        
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Log the error
            log_error(
                error_type="execution_error",
                message=f"Error in {func.__name__}: {str(e)}",
                document_id=document_id,
                exception=e,
                recoverable=kwargs.get('recoverable', True)
            )
            
            # Re-raise if requested
            if kwargs.get('raise_exception', False):
                raise
            
            # Otherwise return failure indicator
            return None
    
    return wrapper

def batch_safe_executor(func):
    """
    Decorator for safely executing a function on a batch of items.
    
    This decorator will ensure that if one item in a batch fails, the others can still be processed.
    
    Args:
        func: Function to decorate
        
    Returns:
        Decorated function
    """
    @wraps(func)
    def wrapper(items, *args, **kwargs):
        results = []
        failed_items = []
        
        for item in items:
            try:
                result = func([item], *args, **kwargs)
                results.extend(result)
            except Exception as e:
                # Log the error
                document_id = None
                if hasattr(item, 'id'):
                    document_id = item.id
                
                log_error(
                    error_type="batch_item_error",
                    message=f"Error processing item in {func.__name__}: {str(e)}",
                    document_id=document_id,
                    exception=e,
                    recoverable=True
                )
                
                failed_items.append(item)
        
        # Return both successful results and failed items
        return results, failed_items
    
    return wrapper

def get_error_stats():
    """
    Get statistics about errors encountered during the rebuild process.
    
    Returns:
        dict: Error statistics
    """
    return {
        "total_errors": ERROR_STATS["total_errors"],
        "errors_by_type": ERROR_STATS["by_type"],
        "errors_by_document": ERROR_STATS["by_document"],
        "recoverable_errors": ERROR_STATS["recoverable_errors"],
        "unrecoverable_errors": ERROR_STATS["unrecoverable_errors"],
        "retryable_documents_count": len(ERROR_STATS["retried_documents"]),
        "failed_documents_count": len(ERROR_STATS["failed_documents"])
    }

@safe_executor
def process_with_error_handling(func, *args, **kwargs):
    """
    Generic function to process something with error handling.
    
    Args:
        func: Function to execute
        *args: Arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function
        
    Returns:
        Result of the function
    """
    return func(*args, **kwargs)