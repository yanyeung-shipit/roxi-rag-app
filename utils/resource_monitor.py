"""
Resource monitoring utilities for ROXI

This module provides functions to monitor system resources and determine
appropriate processing strategies based on available resources.
"""

import psutil
import json
import datetime
import threading
import time
from typing import Dict, Any, Tuple, Optional

# Constants
HIGH_CPU_THRESHOLD = 75.0  # percent
HIGH_MEMORY_THRESHOLD = 80.0  # percent
RESOURCE_UPDATE_INTERVAL = 5  # seconds

# Global state
_resource_data = {
    "cpu_percent": 0.0,
    "memory_percent": 0.0,
    "memory_available_mb": 0.0,
    "last_updated": "",
    "recommended_mode": "single-chunk",
    "recommended_batch_size": 1,
    "resource_limited": True,
    "processing_rate": 0.0,
    "processing_mode": "idle"
}

# Lock for thread safety
_lock = threading.Lock()


def get_system_resources() -> Dict[str, float]:
    """
    Get current system resource usage.
    
    Returns:
        Dict with CPU and memory usage percentages
    """
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_available_mb = memory.available / (1024 * 1024)  # Convert to MB
        
        return {
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "memory_available_mb": round(memory_available_mb, 1)
        }
    except Exception as e:
        print(f"Error getting system resources: {e}")
        # Return conservative estimates if monitoring fails
        return {
            "cpu_percent": 70.0,
            "memory_percent": 70.0,
            "memory_available_mb": 100.0
        }


def determine_processing_mode(resources: Dict[str, float]) -> Tuple[str, int, bool]:
    """
    Determine optimal processing mode based on current resource usage.
    
    Args:
        resources: Dict with CPU and memory usage percentages
        
    Returns:
        Tuple of (processing_mode, batch_size, resource_limited)
    """
    cpu_percent = resources["cpu_percent"]
    memory_percent = resources["memory_percent"]
    
    # Conservative approach - if either resource is high, reduce batch size
    if cpu_percent > HIGH_CPU_THRESHOLD or memory_percent > HIGH_MEMORY_THRESHOLD:
        # Resources are constrained, use single-chunk processing
        return "single-chunk", 1, True
    
    # Calculate a dynamic batch size based on available resources
    # The formula gives higher batch sizes when resources are plentiful
    # and lower batch sizes when resources are more constrained
    cpu_factor = 1 - (cpu_percent / 100)
    memory_factor = 1 - (memory_percent / 100)
    
    # Use the more constrained resource as the limiting factor
    limiting_factor = min(cpu_factor, memory_factor)
    
    # Calculate batch size (1 to 10)
    max_batch_size = 10
    batch_size = max(1, min(max_batch_size, int(limiting_factor * max_batch_size) + 1))
    
    # Determine processing mode based on batch size
    if batch_size > 5:
        mode = "batch (high capacity)"
    elif batch_size > 1:
        mode = "batch (limited capacity)"
    else:
        mode = "single-chunk"
    
    return mode, batch_size, batch_size == 1


def update_resource_data():
    """Update the global resource data."""
    global _resource_data
    resources = get_system_resources()
    mode, batch_size, resource_limited = determine_processing_mode(resources)
    
    with _lock:
        _resource_data.update({
            "cpu_percent": resources["cpu_percent"],
            "memory_percent": resources["memory_percent"],
            "memory_available_mb": resources["memory_available_mb"],
            "last_updated": datetime.datetime.now().isoformat(),
            "recommended_mode": mode,
            "recommended_batch_size": batch_size,
            "resource_limited": resource_limited
        })


def get_resource_data() -> Dict[str, Any]:
    """
    Get the current resource data.
    
    Returns:
        Dict with resource information
    """
    with _lock:
        return _resource_data.copy()


def set_processing_status(mode: str, rate: float):
    """
    Set the current processing status.
    
    Args:
        mode: Current processing mode (e.g., "single-chunk", "batch")
        rate: Processing rate in chunks per second
    """
    with _lock:
        _resource_data["processing_mode"] = mode
        _resource_data["processing_rate"] = rate


def _resource_monitor_thread():
    """Background thread to continuously update resource information."""
    while True:
        try:
            update_resource_data()
        except Exception as e:
            print(f"Error in resource monitor thread: {e}")
        time.sleep(RESOURCE_UPDATE_INTERVAL)


# Start the resource monitoring thread
def start_resource_monitoring():
    """Start the background resource monitoring thread."""
    thread = threading.Thread(target=_resource_monitor_thread, daemon=True)
    thread.start()
    update_resource_data()  # Do initial update
    print("Resource monitoring started")


# Initialize the resource monitoring when imported
if __name__ != "__main__":
    start_resource_monitoring()