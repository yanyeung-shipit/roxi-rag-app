"""
Resource monitoring utilities for ROXI

This module provides functions to monitor system resources and determine
appropriate processing strategies based on available resources.
Enhanced with memory leak detection and memory optimization features.
"""

import psutil
import json
import datetime
import threading
import time
import gc
import logging
from typing import Dict, Any, Tuple, Optional, List

# Restore built-in names in case they were shadowed
import builtins
int = builtins.int
Exception = builtins.Exception

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants - more aggressive memory management
HIGH_CPU_THRESHOLD = 85.0  # percent - increased from 70%
HIGH_MEMORY_THRESHOLD = 85.0  # percent - increased from 80%
CRITICAL_MEMORY_THRESHOLD = 95.0  # percent - threshold for emergency memory cleanup (increased from 80%)
RESOURCE_UPDATE_INTERVAL = 3  # seconds - check more frequently (was 5)
MEMORY_SAMPLE_SIZE = 15  # Number of memory readings to keep for trend analysis (increased from 10)
LEAK_DETECTION_THRESHOLD = 10.0  # MB increase over last readings indicates potential leak (increased from 5.0)

# Global state
_resource_data = {
    "cpu_percent": 0.0,
    "memory_percent": 0.0,
    "memory_available_mb": 0.0,
    "memory_used_mb": 0.0,
    "last_updated": "",
    "recommended_mode": "single-chunk",
    "recommended_batch_size": 1,
    "resource_limited": True,
    "processing_rate": 0.0,
    "processing_mode": "idle",
    "memory_trend": "stable",  # Can be "increasing", "decreasing", or "stable"
    "potential_leak_detected": False,
    "last_emergency_cleanup": None  # Timestamp of last emergency cleanup
}

# Memory history for leak detection
_memory_history: List[float] = []

# Lock for thread safety
_lock = threading.Lock()


def get_system_resources() -> Dict[str, Any]:
    """
    Get current system resource usage.
    
    Returns:
        Dict with CPU and memory usage percentages and detailed memory metrics
    """
    try:
        # Get detailed memory information
        cpu_percent = psutil.cpu_percent(interval=0.5)  # Reduced from 1s to 0.5s for faster response
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_available_mb = memory.available / (1024 * 1024)  # Convert to MB
        memory_used_mb = memory.used / (1024 * 1024)  # Used memory in MB
        
        # Get process-specific memory information for more detailed analysis
        current_process = psutil.Process()
        process_memory_info = current_process.memory_info()
        process_memory_mb = process_memory_info.rss / (1024 * 1024)  # Process RSS memory in MB
        
        # Get detailed memory allocation by category for Python process
        python_memory = {
            "rss_mb": round(process_memory_info.rss / (1024 * 1024), 1),  # Resident Set Size
            "vms_mb": round(process_memory_info.vms / (1024 * 1024), 1),  # Virtual Memory Size
            "shared_mb": round(getattr(process_memory_info, 'shared', 0) / (1024 * 1024), 1),  # Shared memory
            "process_percent": round(current_process.memory_percent(), 1)  # Process memory as % of total
        }
        
        # Try to get even more detailed Python memory info if psutil supports it
        if hasattr(process_memory_info, 'uss'):
            # Unique Set Size - memory unique to this process
            python_memory["uss_mb"] = round(process_memory_info.uss / (1024 * 1024), 1)
        
        if hasattr(process_memory_info, 'pss'):
            # Proportional Set Size - proportional share of shared memory
            python_memory["pss_mb"] = round(process_memory_info.pss / (1024 * 1024), 1)
        
        # Get count of open file descriptors as a leak indicator
        try:
            fd_count = len(current_process.open_files())
            python_memory["open_files"] = fd_count
        except Exception:
            python_memory["open_files"] = -1  # Unable to determine
        
        # Get thread count as another potential leak indicator
        python_memory["thread_count"] = len(current_process.threads())
        
        return {
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "memory_available_mb": round(memory_available_mb, 1),
            "memory_used_mb": round(memory_used_mb, 1),
            "process_memory_mb": round(process_memory_mb, 1),
            "python_memory": python_memory
        }
    except Exception as e:
        logger.error(f"Error getting system resources: {e}")
        # Return conservative estimates if monitoring fails
        return {
            "cpu_percent": 70.0,
            "memory_percent": 70.0,
            "memory_available_mb": 100.0,
            "memory_used_mb": 500.0,
            "process_memory_mb": 300.0,
            "python_memory": {
                "rss_mb": 300.0,
                "vms_mb": 500.0,
                "shared_mb": 50.0,
                "process_percent": 30.0,
                "open_files": 10,
                "thread_count": 5
            }
        }


def determine_processing_mode(resources: Dict[str, Any]) -> Tuple[str, int, bool]:
    """
    Determine optimal processing mode based on current resource usage.
    
    Args:
        resources: Dict with CPU and memory usage percentages and other metrics
        
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


def detect_memory_leak() -> Tuple[bool, str]:
    """
    Analyze memory history to detect potential memory leaks.
    
    Returns:
        Tuple of (leak_detected, trend) where trend is "increasing", "decreasing", or "stable"
    """
    global _memory_history
    
    if len(_memory_history) < MEMORY_SAMPLE_SIZE // 2:  # Need at least half the sample size
        return False, "stable"  # Not enough data
    
    # Look at the trend over the last few samples
    recent_history = _memory_history[-MEMORY_SAMPLE_SIZE:]
    
    if len(recent_history) < 3:  # Need at least 3 points for a trend
        return False, "stable"
    
    # Simple trend detection: compare first half average to second half average
    half_point = len(recent_history) // 2
    first_half_avg = sum(recent_history[:half_point]) / half_point
    second_half_avg = sum(recent_history[half_point:]) / (len(recent_history) - half_point)
    
    delta = second_half_avg - first_half_avg
    
    # Determine trend
    if delta > LEAK_DETECTION_THRESHOLD:
        trend = "increasing"
        # If increasing rapidly, might be a leak
        if delta > LEAK_DETECTION_THRESHOLD * 2:
            return True, trend
    elif delta < -LEAK_DETECTION_THRESHOLD:
        trend = "decreasing"
    else:
        trend = "stable"
    
    return False, trend


def perform_emergency_memory_cleanup():
    """
    Perform ULTRA-AGGRESSIVE emergency memory cleanup when memory usage is critical.
    This implements a comprehensive multi-stage cleanup process to reclaim as much memory
    as possible using every available technique.
    """
    logger.warning("!!! INITIATING MAXIMUM EMERGENCY MEMORY CLEANUP !!!")
    
    # Record memory before cleanup
    pmem = psutil.Process().memory_info()
    before_mb = pmem.rss / (1024 * 1024)
    logger.warning(f"EMERGENCY: Memory before cleanup: {before_mb:.1f}MB")
    
    # ----- STAGE 1: Clear all Python interpreter caches first -----
    
    # Import sys here to fix the "sys is not defined" LSP error
    import sys
    
    # Clear sys module caches
    sys.path_importer_cache.clear()
    
    # Create local references to clear __loader__ and __spec__ attributes
    sys_modules_copy = list(sys.modules.values())
    
    # Clear module loader and spec references which can hold memory
    for module in sys_modules_copy:
        try:
            if hasattr(module, '__loader__') and not module.__loader__ is None:
                module.__loader__ = None
            if hasattr(module, '__spec__') and not module.__spec__ is None:
                module.__spec__ = None
        except:
            pass
    
    # ----- STAGE 2: Clear all application caches -----
    
    # Try to clear embedding cache first (fastest win)
    try:
        from utils.llm_service import clear_embedding_cache
        num_cleared = clear_embedding_cache()
        logger.warning(f"EMERGENCY: Cleared {num_cleared} items from embedding cache")
    except ImportError:
        pass
    
    # ----- STAGE 3: Unload vector store and perform deep cleanup -----
    
    # If that's not enough, try to force vector store unloading and memory reduction
    try:
        from utils.background_processor import reduce_memory_usage
        stats = reduce_memory_usage()
        logger.warning(f"EMERGENCY: Aggressive memory reduction: {stats}")
    except ImportError:
        pass
    
    # ----- STAGE 4: Force deep sleep mode if we're not already in it -----
    
    try:
        from utils.background_processor import is_in_deep_sleep, force_deep_sleep
        
        # Check if we're in deep sleep, and if not, force it
        if not is_in_deep_sleep():
            logger.warning("EMERGENCY: Forcing deep sleep mode to conserve memory")
            force_deep_sleep()
    except ImportError:
        pass
    
    # ----- STAGE 4: Aggressive garbage collection and memory defragmentation -----
    
    # Run multiple garbage collection passes
    gc.collect(generation=2)
    gc.collect(generation=1)
    gc.collect(generation=0)
    
    # Try to break reference cycles
    try:
        # Get count of objects before clearing cycles
        objects_before = len(gc.get_objects())
        
        # Clear dictionary objects (common source of reference cycles)
        for obj in gc.get_objects():
            try:
                if isinstance(obj, dict) and not hasattr(obj, '__dict__'):
                    obj.clear()
            except:
                pass
        
        # Run another collection to clean up the cleared dictionaries
        gc.collect(generation=2)
        
        # Get count after to see if we made progress
        objects_after = len(gc.get_objects())
        logger.warning(f"EMERGENCY: Cleared {objects_before - objects_after} objects through cycle breaking")
    except Exception as e:
        logger.error(f"Error during reference cycle clearing: {e}")
    
    # ----- STAGE 5: OS-level memory trimming -----
    
    # Try to return memory to the OS using malloc_trim
    try:
        import ctypes
        try:
            libc = ctypes.CDLL('libc.so.6')
            if hasattr(libc, 'malloc_trim'):
                result = libc.malloc_trim(0)
                logger.warning(f"EMERGENCY: Called malloc_trim(0) to release memory to OS: result={result}")
        except:
            pass
    except:
        pass
    
    # ----- STAGE 6: Final memory reporting -----
    
    # Get memory usage after cleanup
    try:
        process = psutil.Process()
        after_mem = process.memory_info().rss / (1024 * 1024)  # MB
        
        # Get system memory
        system_memory = psutil.virtual_memory()
        system_memory_percent = system_memory.percent
        
        logger.warning(f"EMERGENCY CLEANUP COMPLETE - Process memory: {after_mem:.1f}MB, System: {system_memory_percent:.1f}%")
    except:
        logger.warning("EMERGENCY CLEANUP COMPLETE - Unable to get memory statistics")
    
    # Update timestamp of last cleanup
    with _lock:
        _resource_data["last_emergency_cleanup"] = datetime.datetime.now().isoformat()


def update_resource_data():
    """Update the global resource data with enhanced memory trend analysis."""
    global _resource_data, _memory_history
    
    # Get current resource data
    resources = get_system_resources()
    mode, batch_size, resource_limited = determine_processing_mode(resources)
    
    # Check for critical memory conditions
    memory_percent = resources["memory_percent"]
    process_memory_mb = resources.get("process_memory_mb", 0)
    
    # Record process memory for trend analysis
    if process_memory_mb > 0:
        _memory_history.append(process_memory_mb)
        # Keep history size limited
        if len(_memory_history) > MEMORY_SAMPLE_SIZE * 2:  # Keep double the sample size for longer trends
            _memory_history = _memory_history[-MEMORY_SAMPLE_SIZE * 2:]
    
    # Detect potential memory leaks
    leak_detected, memory_trend = detect_memory_leak()
    
    # Check if we need emergency cleanup
    needs_cleanup = False
    if memory_percent > CRITICAL_MEMORY_THRESHOLD:
        logger.warning(f"Critical memory usage detected: {memory_percent}%")
        needs_cleanup = True
    
    if leak_detected:
        logger.warning(f"Potential memory leak detected! Memory trend: {memory_trend}")
        needs_cleanup = True
    
    # Get last cleanup time, if any
    last_cleanup = None
    with _lock:
        last_cleanup = _resource_data.get("last_emergency_cleanup")
    
    # Perform emergency cleanup if needed and not done recently
    if needs_cleanup:
        # Check if we've done a cleanup recently (within last 5 minutes)
        current_time = datetime.datetime.now()
        if last_cleanup:
            try:
                last_cleanup_time = datetime.datetime.fromisoformat(last_cleanup)
                time_since_cleanup = (current_time - last_cleanup_time).total_seconds()
                if time_since_cleanup < 300:  # 5 minutes in seconds
                    needs_cleanup = False  # Don't do another cleanup too soon
            except (ValueError, TypeError):
                # Invalid timestamp, proceed with cleanup
                pass
        
        if needs_cleanup:
            perform_emergency_memory_cleanup()
    
    # Update resource data
    with _lock:
        _resource_data.update({
            "cpu_percent": resources["cpu_percent"],
            "memory_percent": resources["memory_percent"],
            "memory_available_mb": resources["memory_available_mb"],
            "memory_used_mb": resources.get("memory_used_mb", 0),
            "process_memory_mb": process_memory_mb,
            "python_memory": resources.get("python_memory", {}),
            "last_updated": datetime.datetime.now().isoformat(),
            "recommended_mode": mode,
            "recommended_batch_size": batch_size,
            "resource_limited": resource_limited,
            "memory_trend": memory_trend,
            "potential_leak_detected": leak_detected
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
    """
    Background thread to continuously update resource information with enhanced monitoring.
    This thread performs:
    1. Regular resource data updates
    2. Periodic memory leak detection
    3. Emergency memory cleanup when necessary
    4. Detailed logging for troubleshooting
    """
    counter = 0
    log_interval = 12  # Log detailed stats every ~60 seconds (12 * 5s intervals) 
    
    while True:
        try:
            # Update resource data
            update_resource_data()
            
            # Increment counter for periodic logging
            counter += 1
            
            # Periodically log detailed resource information for trend analysis
            if counter % log_interval == 0:
                with _lock:
                    resource_snapshot = _resource_data.copy()
                
                # Get process-specific memory info for detailed logging
                if "python_memory" in resource_snapshot:
                    python_mem = resource_snapshot["python_memory"]
                    memory_details = (
                        f"Memory: {resource_snapshot['memory_percent']:.1f}% used, "
                        f"Process: {resource_snapshot['process_memory_mb']:.1f}MB, "
                        f"RSS: {python_mem.get('rss_mb', 0):.1f}MB, "
                        f"Open files: {python_mem.get('open_files', 'unknown')}, "
                        f"Threads: {python_mem.get('thread_count', 'unknown')}, "
                        f"Trend: {resource_snapshot.get('memory_trend', 'unknown')}"
                    )
                    
                    # Log memory usage trends for debugging
                    logger.info(f"Resource snapshot - {memory_details}")
                    
                    # Check for potential leaks and log them at WARNING level
                    if resource_snapshot.get('potential_leak_detected', False):
                        logger.warning(
                            f"Memory trend analysis indicates potential leak: "
                            f"{memory_details}"
                        )
                
                # Every ~5 minutes, perform a full memory analysis
                if counter % (log_interval * 5) == 0:
                    # Force garbage collection and memory analysis
                    gc.collect()
                    
                    # Log memory history for trend analysis
                    if len(_memory_history) >= 5:
                        recent_history = _memory_history[-5:]
                        logger.info(f"Memory history (last 5 readings): {recent_history}")
                        
                        # Calculate rate of change
                        if len(recent_history) >= 2:
                            change_rate = (recent_history[-1] - recent_history[0]) / len(recent_history)
                            logger.info(f"Memory change rate: {change_rate:.2f}MB per interval")
                    
                    # Reset counter to prevent integer overflow in long-running processes
                    if counter > 1000:
                        counter = 0
            
        except Exception as e:
            logger.error(f"Resource monitor thread error: {str(e)}")
            logger.error("Resource monitoring disabled due to error")
            # Don't crash the application, just disable monitoring
            time.sleep(60)  # Sleep to prevent tight error loops
        
        # Sleep until next update
        time.sleep(RESOURCE_UPDATE_INTERVAL)


# Start the resource monitoring thread
def start_resource_monitoring():
    """
    Start the background resource monitoring thread with enhanced logging.
    This initializes memory tracking and leak detection systems.
    """
    # Perform initial resource update and memory tracking
    update_resource_data()
    
    # Log initial resource state
    with _lock:
        resource_snapshot = _resource_data.copy()
    
    # Log detailed initial resource state
    mem_percent = resource_snapshot["memory_percent"]
    mem_available_mb = resource_snapshot["memory_available_mb"]
    
    logger.info(f"Starting resource monitoring: Memory {mem_percent:.1f}% used, {mem_available_mb:.1f}MB available")
    
    # Start monitoring thread
    thread = threading.Thread(
        target=_resource_monitor_thread, 
        daemon=True,
        name="ResourceMonitorThread"  # Named thread for easier debugging
    )
    thread.start()
    
    # Log memory optimization settings
    logger.info(
        f"Memory monitoring initialized with: "
        f"HIGH_THRESHOLD={HIGH_MEMORY_THRESHOLD}%, "
        f"CRITICAL_THRESHOLD={CRITICAL_MEMORY_THRESHOLD}%, "
        f"LEAK_THRESHOLD={LEAK_DETECTION_THRESHOLD}MB, "
        f"SAMPLE_SIZE={MEMORY_SAMPLE_SIZE}"
    )


# Initialize the resource monitoring when imported
if __name__ != "__main__":
    start_resource_monitoring()
