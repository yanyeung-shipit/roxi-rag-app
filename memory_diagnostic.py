import os
import sys
import gc
import time
import json
import logging
import psutil
import threading
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_memory_profile():
    """
    Get detailed memory profile of the current process.
    
    Returns:
        dict: Detailed memory usage information
    """
    process = psutil.Process()
    memory_info = process.memory_info()
    
    # Get system memory information
    system_memory = psutil.virtual_memory()
    
    # Get Python object counts to identify potential memory issues
    object_counts = {}
    
    # Collect garbage to get more accurate results
    gc.collect()
    
    # Get statistics on Python objects
    for obj_type in [str, dict, list, set, tuple]:
        object_counts[obj_type.__name__] = sum(1 for o in gc.get_objects() if type(o) is obj_type)
    
    # Count total number of objects
    total_objects = len(gc.get_objects())
    
    profile = {
        "system": {
            "total_memory_mb": system_memory.total / (1024 * 1024),
            "available_memory_mb": system_memory.available / (1024 * 1024),
            "used_memory_mb": system_memory.used / (1024 * 1024),
            "memory_percent": system_memory.percent
        },
        "process": {
            "rss_mb": memory_info.rss / (1024 * 1024),  # Resident Set Size
            "vms_mb": memory_info.vms / (1024 * 1024),  # Virtual Memory Size
            "shared_mb": getattr(memory_info, 'shared', 0) / (1024 * 1024),
            "text_mb": getattr(memory_info, 'text', 0) / (1024 * 1024),
            "data_mb": getattr(memory_info, 'data', 0) / (1024 * 1024),
            "lib_mb": getattr(memory_info, 'lib', 0) / (1024 * 1024),
            "dirty_mb": getattr(memory_info, 'dirty', 0) / (1024 * 1024),
            "process_percent": process.memory_percent()
        },
        "python": {
            "object_counts": object_counts,
            "total_objects": total_objects,
            "garbage_collector": gc.get_stats(),
            "malloc_stats": gc.get_stats()
        },
        "timestamp": time.time()
    }
    
    # Try to get unique memory stats if available
    try:
        if hasattr(memory_info, 'uss'):
            profile["process"]["uss_mb"] = memory_info.uss / (1024 * 1024)  # Unique Set Size
        if hasattr(memory_info, 'pss'):
            profile["process"]["pss_mb"] = memory_info.pss / (1024 * 1024)  # Proportional Set Size
    except:
        pass
    
    return profile

def get_top_modules_by_memory():
    """
    Estimate memory usage by loaded Python modules.
    This is an approximation - modules with many references will show higher usage.
    
    Returns:
        list: Top modules by approximate memory usage
    """
    import sys
    import inspect
    from types import ModuleType
    
    # Get all loaded modules
    modules = list(sys.modules.values())
    
    # Collect memory estimates for each module
    module_sizes = []
    for module in modules:
        try:
            if not isinstance(module, ModuleType):
                continue
            
            # Get module name
            module_name = getattr(module, '__name__', str(module))
            
            # Count objects owned by this module
            object_count = 0
            size_estimate = 0
            
            # Count variables defined in the module
            try:
                for name, obj in inspect.getmembers(module):
                    object_count += 1
                    # Very crude size estimate based on type
                    if isinstance(obj, (str, bytes)):
                        size_estimate += len(obj)
                    elif isinstance(obj, (list, tuple, set)):
                        try:
                            size_estimate += len(obj) * 8  # Rough estimate
                        except:
                            pass
                    elif isinstance(obj, dict):
                        try:
                            size_estimate += len(obj) * 16  # Rough estimate
                        except:
                            pass
                    elif hasattr(obj, '__sizeof__'):
                        try:
                            size_estimate += obj.__sizeof__()
                        except:
                            pass
            except:
                pass
            
            # Add to list if we have meaningful data
            if object_count > 0:
                module_sizes.append({
                    'module': module_name,
                    'object_count': object_count,
                    'size_estimate_kb': size_estimate / 1024
                })
            
        except:
            continue
    
    # Sort by estimated size
    return sorted(module_sizes, key=lambda x: x['size_estimate_kb'], reverse=True)[:30]

def get_vector_store_info():
    """
    Get information about the vector store.
    
    Returns:
        dict: Vector store information
    """
    try:
        # Import lazily to avoid unnecessary imports
        from utils.vector_store import VectorStore
        
        # Create vector store instance - should load from disk
        vector_store = VectorStore()
        
        # Get basic stats
        stats = vector_store.get_stats()
        
        # Check if document data is loaded
        documents_loaded = len(vector_store.documents) > 0
        
        # Get information about document metadata structure
        metadata_keys = set()
        if documents_loaded and hasattr(vector_store, 'documents'):
            doc_sample = next(iter(vector_store.documents.values()), {})
            if isinstance(doc_sample, dict) and 'metadata' in doc_sample:
                metadata_keys = set(doc_sample['metadata'].keys())
        
        return {
            'documents_loaded': documents_loaded,
            'stats': stats,
            'metadata_keys': list(metadata_keys)
        }
    except Exception as e:
        logger.exception(f"Error getting vector store info: {e}")
        return {
            'error': str(e)
        }

def get_embedding_cache_info():
    """
    Get information about the embedding cache.
    
    Returns:
        dict: Embedding cache information
    """
    try:
        from utils.llm_service import get_embedding_cache_stats
        return get_embedding_cache_stats()
    except Exception as e:
        logger.exception(f"Error getting embedding cache info: {e}")
        return {
            'error': str(e)
        }

def get_deep_sleep_status():
    """
    Check if the background processor is in deep sleep mode.
    
    Returns:
        dict: Deep sleep status information
    """
    try:
        from utils.background_processor import is_in_deep_sleep, get_processor_status
        
        deep_sleep = is_in_deep_sleep()
        status = get_processor_status()
        
        return {
            'in_deep_sleep': deep_sleep,
            'status': status
        }
    except Exception as e:
        logger.exception(f"Error getting deep sleep status: {e}")
        return {
            'error': str(e)
        }

def collect_diagnostic_info():
    """
    Collect comprehensive diagnostic information about memory usage.
    
    Returns:
        dict: Complete diagnostic information
    """
    # Start with memory profile
    info = {
        'memory_profile': get_memory_profile(),
        'top_modules': get_top_modules_by_memory(),
        'vector_store': get_vector_store_info(),
        'embedding_cache': get_embedding_cache_info(),
        'deep_sleep': get_deep_sleep_status()
    }
    
    # Add resource monitor data if available
    try:
        from utils.resource_monitor import get_resource_data
        info['resource_monitor'] = get_resource_data()
    except:
        info['resource_monitor'] = {'error': 'Resource monitor data not available'}
    
    return info

if __name__ == "__main__":
    # Get diagnostic info
    diagnostic_info = collect_diagnostic_info()
    
    # Print summary to console
    print("\n" + "="*80)
    print("MEMORY DIAGNOSTIC SUMMARY")
    print("="*80)
    
    # System memory
    system = diagnostic_info['memory_profile']['system']
    print(f"\nSYSTEM MEMORY:")
    print(f"  Total:     {system['total_memory_mb']:.1f} MB")
    print(f"  Used:      {system['used_memory_mb']:.1f} MB ({system['memory_percent']:.1f}%)")
    print(f"  Available: {system['available_memory_mb']:.1f} MB")
    
    # Process memory
    process = diagnostic_info['memory_profile']['process']
    print(f"\nPROCESS MEMORY:")
    print(f"  RSS:       {process['rss_mb']:.1f} MB")
    print(f"  VMS:       {process['vms_mb']:.1f} MB")
    
    if 'uss_mb' in process:
        print(f"  USS:       {process['uss_mb']:.1f} MB (unique)")
    
    print(f"  Percent:   {process['process_percent']:.1f}% of system memory")
    
    # Python objects
    python = diagnostic_info['memory_profile']['python']
    print(f"\nPYTHON OBJECTS:")
    for obj_type, count in python['object_counts'].items():
        print(f"  {obj_type:6s}: {count:,}")
    print(f"  TOTAL:    {python['total_objects']:,}")
    
    # Vector store info
    vector_store = diagnostic_info['vector_store']
    print(f"\nVECTOR STORE:")
    if 'error' in vector_store:
        print(f"  Error: {vector_store['error']}")
    else:
        print(f"  Documents loaded: {vector_store['documents_loaded']}")
        if 'stats' in vector_store:
            stats = vector_store['stats']
            print(f"  Total chunks:    {stats.get('chunks', 0)}")
            print(f"  PDFs:            {stats.get('pdfs', 0)}")
            print(f"  Websites:        {stats.get('websites', 0)}")
    
    # Deep sleep status
    deep_sleep = diagnostic_info['deep_sleep']
    print(f"\nBACKGROUND PROCESSOR:")
    if 'error' in deep_sleep:
        print(f"  Error: {deep_sleep['error']}")
    else:
        print(f"  Deep sleep mode: {'Yes' if deep_sleep.get('in_deep_sleep', False) else 'No'}")
        if 'status' in deep_sleep:
            status = deep_sleep['status']
            print(f"  Status: {status.get('status', 'Unknown')}")
    
    print("\n" + "="*80)
    
    # Optionally write full diagnostic info to a file
    with open('memory_diagnostic.json', 'w') as f:
        json.dump(diagnostic_info, f, indent=2)
    
    print(f"Complete diagnostic information written to memory_diagnostic.json")
    print("="*80 + "\n")