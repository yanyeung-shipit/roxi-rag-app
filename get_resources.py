#!/usr/bin/env python3
"""
Memory resources diagnostic script. Provides a snapshot of current system resources
and helps identify potential memory leaks or excessive resource usage.

This simplified version focuses on memory usage metrics and produces clean output
suitable for quick system health checks.
"""

import os
import sys
import gc
import time
import json
import logging
import psutil
import argparse
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def format_size(size_bytes: int) -> str:
    """Format bytes into human-readable size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

def get_memory_usage() -> Dict[str, Any]:
    """Get memory usage information."""
    process = psutil.Process()
    memory_info = process.memory_info()
    
    # Get system memory information
    system_memory = psutil.virtual_memory()
    
    memory_data = {
        "system": {
            "total": format_size(system_memory.total),
            "available": format_size(system_memory.available),
            "used": format_size(system_memory.used),
            "percent": system_memory.percent
        },
        "process": {
            "rss": format_size(memory_info.rss),
            "vms": format_size(memory_info.vms),
            "process_percent": process.memory_percent()
        }
    }
    
    # Try to get unique memory stats if available
    try:
        if hasattr(memory_info, 'uss'):
            memory_data["process"]["uss"] = format_size(memory_info.uss)
        if hasattr(memory_info, 'pss'):
            memory_data["process"]["pss"] = format_size(memory_info.pss)
    except:
        pass
    
    return memory_data

def get_python_objects() -> Dict[str, int]:
    """Get counts of Python objects."""
    # Collect garbage to get more accurate results
    gc.collect()
    
    # Count common object types
    object_counts = {}
    for obj_type in [str, dict, list, set, tuple]:
        object_counts[obj_type.__name__] = sum(1 for o in gc.get_objects() if type(o) is obj_type)
    
    # Count total number of objects
    object_counts["total"] = len(gc.get_objects())
    
    return object_counts

def get_process_info() -> Dict[str, Any]:
    """Get information about the current process."""
    process = psutil.Process()
    
    # Get open files
    try:
        open_files = len(process.open_files())
    except:
        open_files = "N/A"
    
    # Get threads
    try:
        threads = len(process.threads())
    except:
        threads = "N/A"
    
    # Get basic process info
    return {
        "pid": process.pid,
        "name": process.name(),
        "cpu_percent": process.cpu_percent(interval=0.1),
        "threads": threads,
        "open_files": open_files,
        "create_time": time.strftime('%Y-%m-%d %H:%M:%S', 
                                   time.localtime(process.create_time()))
    }

def get_system_info() -> Dict[str, Any]:
    """Get basic system information."""
    return {
        "cpu_count": psutil.cpu_count(),
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "boot_time": time.strftime('%Y-%m-%d %H:%M:%S', 
                                 time.localtime(psutil.boot_time()))
    }

def check_memory_leaks() -> Dict[str, Any]:
    """Basic check for potential memory leaks."""
    # Get baseline object counts
    gc.collect()
    initial_counts = get_python_objects()
    
    # Force collection again
    gc.collect()
    gc.collect()
    
    # Get counts after collection
    after_counts = get_python_objects()
    
    # Calculate differences
    differences = {}
    for obj_type, count in after_counts.items():
        initial = initial_counts.get(obj_type, 0)
        diff = count - initial
        if diff != 0:
            differences[obj_type] = diff
    
    # Check for garbage
    garbage_count = len(gc.garbage)
    
    return {
        "object_count_changes": differences if differences else "No changes detected",
        "garbage_objects": garbage_count,
        "potential_leak": garbage_count > 0 or bool(differences)
    }

def get_vector_store_status() -> Dict[str, Any]:
    """Get status of the vector store."""
    try:
        from utils.vector_store import VectorStore
        vs = VectorStore()
        return vs.get_stats()
    except Exception as e:
        return {"error": str(e)}

def get_background_processor_status() -> Dict[str, Any]:
    """Get status of the background processor."""
    try:
        from utils.background_processor import get_processor_status
        return get_processor_status()
    except Exception as e:
        return {"error": str(e)}

def get_embedding_cache_status() -> Dict[str, Any]:
    """Get status of the embedding cache."""
    try:
        from utils.llm_service import get_embedding_cache_stats
        return get_embedding_cache_stats()
    except Exception as e:
        return {"error": str(e)}

def get_all_resource_data() -> Dict[str, Any]:
    """Get all resource data in a structured format."""
    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "memory": get_memory_usage(),
        "process": get_process_info(),
        "system": get_system_info(),
        "python_objects": get_python_objects(),
        "memory_leak_check": check_memory_leaks(),
        "vector_store": get_vector_store_status(),
        "background_processor": get_background_processor_status(),
        "embedding_cache": get_embedding_cache_status()
    }

def print_colored(text: str, color: str = "default") -> None:
    """Print colored text if supported by the terminal."""
    colors = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "magenta": "\033[95m",
        "cyan": "\033[96m",
        "default": "\033[0m",
    }
    
    end_color = "\033[0m"
    
    if color in colors:
        print(f"{colors[color]}{text}{end_color}")
    else:
        print(text)

def print_section_header(title: str) -> None:
    """Print a formatted section header."""
    print("\n" + "="*80)
    print_colored(f" {title.upper()} ", "cyan")
    print("="*80)

def print_summary(data: Dict[str, Any]) -> None:
    """Print a human-readable summary of resource data."""
    print_section_header("SYSTEM RESOURCES SUMMARY")
    
    # Memory usage
    print_colored("\n💾 Memory Usage:", "magenta")
    memory = data["memory"]
    system_mem = memory["system"]
    process_mem = memory["process"]
    
    print(f"  System: {system_mem['used']} / {system_mem['total']} ({system_mem['percent']}%)")
    print(f"  Process: {process_mem['rss']} ({process_mem['process_percent']:.1f}% of system)")
    
    if "uss" in process_mem:
        print(f"  Unique memory (USS): {process_mem['uss']}")
    
    # Determine memory status
    if system_mem["percent"] > 90:
        print_colored("  ⚠️ WARNING: System memory usage is very high!", "red")
    elif system_mem["percent"] > 75:
        print_colored("  ⚠️ CAUTION: System memory usage is elevated.", "yellow")
    else:
        print_colored("  ✅ System memory usage is normal.", "green")
    
    # Process info
    print_colored("\n🔄 Process Info:", "magenta")
    process = data["process"]
    print(f"  PID: {process['pid']} ({process['name']})")
    print(f"  CPU Usage: {process['cpu_percent']:.1f}%")
    print(f"  Threads: {process['threads']}")
    print(f"  Open files: {process['open_files']}")
    print(f"  Started: {process['create_time']}")
    
    # Python objects
    print_colored("\n📊 Python Objects:", "magenta")
    objects = data["python_objects"]
    print(f"  Strings: {objects['str']:,}")
    print(f"  Dictionaries: {objects['dict']:,}")
    print(f"  Lists: {objects['list']:,}")
    print(f"  Sets: {objects['set']:,}")
    print(f"  Tuples: {objects['tuple']:,}")
    print(f"  Total objects: {objects['total']:,}")
    
    # Vector store status
    print_colored("\n📚 Vector Store:", "magenta")
    vector_store = data["vector_store"]
    if "error" in vector_store:
        print_colored(f"  Error: {vector_store['error']}", "red")
    else:
        print(f"  Total chunks: {vector_store.get('chunks', 0)}")
        print(f"  PDFs: {vector_store.get('pdfs', 0)}")
        print(f"  Websites: {vector_store.get('websites', 0)}")
    
    # Background processor status
    print_colored("\n⚙️ Background Processor:", "magenta")
    bg = data["background_processor"]
    if "error" in bg:
        print_colored(f"  Error: {bg['error']}", "red")
    else:
        sleep_mode = "DEEP SLEEP" if bg.get("in_deep_sleep", False) else "ACTIVE"
        status_color = "blue" if sleep_mode == "DEEP SLEEP" else "green"
        print_colored(f"  Status: {sleep_mode}", status_color)
        print(f"  Vector store unloaded: {bg.get('vector_store_unloaded', 'Unknown')}")
        print(f"  Sleep time: {bg.get('sleep_time', 'Unknown')}s")
        print(f"  Documents processed: {bg.get('documents_processed', 0)}")
    
    # Embedding cache status
    print_colored("\n🧠 Embedding Cache:", "magenta")
    cache = data["embedding_cache"]
    if "error" in cache:
        print_colored(f"  Error: {cache['error']}", "red")
    else:
        print(f"  Entries: {cache.get('entries', 0)}")
        print(f"  TTL: {cache.get('ttl_seconds', 0)}s")
        print(f"  Memory limit: {cache.get('memory_limit_mb', 0)}MB")
    
    # Memory leak check
    print_colored("\n🔍 Memory Leak Check:", "magenta")
    leak_check = data["memory_leak_check"]
    leak_detected = leak_check["potential_leak"]
    garbage_count = leak_check["garbage_objects"]
    
    if leak_detected:
        print_colored(f"  ⚠️ Potential memory leak detected!", "yellow")
        print(f"  Garbage objects: {garbage_count}")
        if isinstance(leak_check["object_count_changes"], dict):
            for obj_type, change in leak_check["object_count_changes"].items():
                print(f"  {obj_type}: {change:+d}")
    else:
        print_colored("  ✅ No indication of memory leaks.", "green")
    
    print("\n" + "="*80)
    
    # Attribution and timestamp
    print(f"\nSnapshot taken at: {data['timestamp']}")
    print("="*80 + "\n")

def main() -> None:
    """Main function to print resource summary or save to file."""
    parser = argparse.ArgumentParser(description="Memory resources diagnostic tool")
    parser.add_argument("--json", help="Save data to this JSON file")
    parser.add_argument("--summary", action="store_true", help="Print summary to console (default)")
    args = parser.parse_args()
    
    # Get all resource data
    data = get_all_resource_data()
    
    # Print summary (default action)
    if args.summary or not args.json:
        print_summary(data)
    
    # Save to JSON if requested
    if args.json:
        try:
            with open(args.json, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"Resource data saved to {args.json}")
        except Exception as e:
            print(f"Error saving data to {args.json}: {e}")

if __name__ == "__main__":
    main()