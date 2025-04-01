import os
import time
import random
import logging
import threading
import gc
import psutil
import sys
from datetime import datetime, timedelta
from models import Document, DocumentChunk

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Lazy loading system for imports
def _lazy_import(module_name):
    """Lazily import a module only when it's needed."""
    return __import__(module_name, fromlist=['*'])

# Global variables
DATABASE_URL = os.environ.get("DATABASE_URL")
_engine = None
_Session = None
_vector_store = None
_background_processor = None

# Lazy initialization functions
def get_engine():
    global _engine
    if _engine is None:
        sqlalchemy = _lazy_import('sqlalchemy')
        _engine = sqlalchemy.create_engine(DATABASE_URL)
    return _engine

def get_session_factory():
    global _Session
    if _Session is None:
        sqlalchemy_orm = _lazy_import('sqlalchemy.orm')
        session_factory = sqlalchemy_orm.sessionmaker(bind=get_engine())
        _Session = sqlalchemy_orm.scoped_session(session_factory)
    return _Session

def get_vector_store():
    global _vector_store
    if _vector_store is None:
        vector_store_module = _lazy_import('utils.vector_store')
        _vector_store = vector_store_module.VectorStore()
    return _vector_store

# Pre-configured singleton instance, will be set at the end of the file
background_processor = None

def reduce_memory_usage():
    """
    ULTRA-AGGRESSIVELY reduce memory usage by clearing all caches, unloading components,
    forcing garbage collection, and using advanced memory optimization techniques.
    This is the nuclear option for memory reduction, using every available technique
    to minimize the memory footprint of the application.
    
    Returns:
        dict: Memory statistics before and after reduction
    """
    import gc
    import psutil
    import sys
    import os
    import weakref
    
    # Get before stats
    process = psutil.Process()
    before_mem = process.memory_info().rss / 1024 / 1024  # MB
    
    logger.warning(f"ULTRA-AGGRESSIVE memory optimization starting: {before_mem:.1f} MB in use")
    
    # ----- PHASE 1: CLEAR ALL APPLICATION CACHES -----
    
    # Clear embedding cache if available - most critical for memory reduction
    try:
        from utils.llm_service import clear_embedding_cache
        cache_entries = clear_embedding_cache()
        logger.warning(f"ULTRA: Cleared {cache_entries} entries from embedding cache")
    except Exception as e:
        logger.warning(f"Failed to clear embedding cache: {str(e)}")
    
    # Clear Flask caches if present
    if 'flask' in sys.modules:
        try:
            if 'app' in sys.modules:
                app_module = sys.modules['app']
                if hasattr(app_module, 'app') and hasattr(app_module.app, 'config'):
                    # Clear ALL Flask caches
                    for config_key in list(app_module.app.config.keys()):
                        if 'CACHE' in config_key or 'cache' in config_key.lower():
                            if isinstance(app_module.app.config[config_key], bool):
                                app_module.app.config[config_key] = False
                            elif isinstance(app_module.app.config[config_key], dict):
                                app_module.app.config[config_key] = {}
                    
                    # Set explicit SQLAlchemy cache settings
                    if 'SQLALCHEMY_RECORD_QUERIES' in app_module.app.config:
                        app_module.app.config['SQLALCHEMY_RECORD_QUERIES'] = False
                    
                    logger.warning("ULTRA: Reset ALL Flask cache settings")
        except Exception as e:
            logger.warning(f"Failed to reset Flask caches: {str(e)}")
    
    # ----- PHASE 2: UNLOAD ALL LARGE COMPONENTS -----
    
    # Completely unload vector store from memory as first priority
    global _background_processor
    if _background_processor:
        try:
            # Access the vector store instance and unload it completely
            if hasattr(_background_processor, 'vector_store') and _background_processor.vector_store:
                logger.warning("ULTRA: Completely unloading vector store from memory")
                
                # First call the formal unload method
                docs_unloaded = _background_processor.vector_store.unload()
                logger.warning(f"ULTRA: Unloaded {docs_unloaded} documents from vector store")
                
                # Mark vector store as unloaded so we know to reload it when needed
                _background_processor.vector_store_unloaded = True
                
                # Now go deeper - completely clear all attributes that might hold references
                if hasattr(_background_processor.vector_store, 'documents'):
                    _background_processor.vector_store.documents = {}
                
                if hasattr(_background_processor.vector_store, 'document_counts'):
                    _background_processor.vector_store.document_counts = {}
                
                # Remove FAISS index completely and recreate minimal empty one
                if hasattr(_background_processor.vector_store, 'index'):
                    try:
                        # First destroy existing index
                        del _background_processor.vector_store.index
                        
                        # Then create a minimal replacement
                        import faiss
                        _background_processor.vector_store.index = faiss.IndexFlatL2(_background_processor.vector_store.dimension)
                        logger.warning("ULTRA: Recreated minimal empty FAISS index")
                    except Exception as ex:
                        logger.warning(f"Failed to recreate FAISS index: {str(ex)}")
                
                # Clear any class-level caches that might exist
                for attr_name in dir(_background_processor.vector_store):
                    if 'cache' in attr_name.lower():
                        try:
                            setattr(_background_processor.vector_store, attr_name, {})
                            logger.debug(f"ULTRA: Cleared vector store cache attribute: {attr_name}")
                        except:
                            pass
        except Exception as e:
            logger.warning(f"Failed to fully unload vector store: {str(e)}")
    
    # ----- PHASE 3: CLEAR ALL MODULE-SPECIFIC CACHES -----
    
    # Find and clear ANY module with cache-like attributes
    for module_name in list(sys.modules.keys()):
        try:
            module = sys.modules[module_name]
            
            # Skip None modules or built-in modules that can't be modified
            if module is None or not hasattr(module, '__dict__'):
                continue
                
            # Look for cache-like attributes to clear
            for attr_name in dir(module):
                if ('cache' in attr_name.lower() or 
                    'pool' in attr_name.lower() or 
                    'buffer' in attr_name.lower()):
                    try:
                        attr = getattr(module, attr_name)
                        # Only clear if it looks like a cache (dict or list-like)
                        if hasattr(attr, 'clear') and callable(attr.clear):
                            attr.clear()
                            logger.debug(f"ULTRA: Cleared cache in module {module_name}.{attr_name}")
                        elif isinstance(attr, dict):
                            setattr(module, attr_name, {})
                            logger.debug(f"ULTRA: Reset dict cache in module {module_name}.{attr_name}")
                        elif isinstance(attr, list):
                            setattr(module, attr_name, [])
                            logger.debug(f"ULTRA: Reset list cache in module {module_name}.{attr_name}")
                    except:
                        # Skip attributes that can't be modified
                        pass
        except:
            # Skip problematic modules
            pass
    
    # Clear OpenAI module caches specifically
    if 'openai' in sys.modules:
        try:
            # Reset thread pool if it exists
            if hasattr(sys.modules['openai'], '_Thread__initialized'):
                sys.modules['openai']._Thread__initialized = False
                logger.warning("ULTRA: Reset OpenAI thread pool")
                
            # Clear any OpenAI caches
            openai_module = sys.modules['openai']
            for attr in dir(openai_module):
                if (attr.startswith('_cache') or attr.endswith('_cache') or 
                    'pool' in attr.lower()):
                    try:
                        setattr(openai_module, attr, {})
                        logger.debug(f"ULTRA: Cleared OpenAI cache attribute: {attr}")
                    except:
                        pass
        except Exception as e:
            logger.warning(f"Failed to reset OpenAI caches: {str(e)}")
    
    # Clear NumPy caches if present
    if 'numpy' in sys.modules:
        try:
            np = sys.modules['numpy']
            # Clear all NumPy caches we can find
            for component in ['core', 'lib', 'linalg', 'fft']:
                if hasattr(np, component):
                    component_obj = getattr(np, component)
                    for attr in dir(component_obj):
                        if 'cache' in attr.lower():
                            try:
                                cache_obj = getattr(component_obj, attr)
                                if hasattr(cache_obj, 'clear'):
                                    cache_obj.clear()
                                elif isinstance(cache_obj, dict):
                                    setattr(component_obj, attr, {})
                                logger.debug(f"ULTRA: Cleared NumPy {component}.{attr} cache")
                            except:
                                pass
            
            # Clear ctypes cache which often contains large memory blocks
            if hasattr(np, 'core') and hasattr(np.core, '_internal'):
                if hasattr(np.core._internal, '_ctypes'):
                    del np.core._internal._ctypes
                    logger.warning("ULTRA: Cleared NumPy internal ctypes cache")
        except Exception as e:
            logger.warning(f"Failed to clear NumPy caches: {str(e)}")
    
    # ----- PHASE 4: DESTROY ALL DATABASE CONNECTIONS -----
    
    # Completely destroy all SQLAlchemy connection pools
    if 'sqlalchemy' in sys.modules:
        try:
            from sqlalchemy import event
            from sqlalchemy.engine import Engine
            
            # First try with background processor engine
            engine = _background_processor.engine if _background_processor else None
            if engine:
                # Dispose connections completely and aggressively
                engine.dispose()
                logger.warning("ULTRA: SQLAlchemy background processor connection pool disposed")
            
            # Try to clear app-level connection pool if it exists
            if 'app' in sys.modules:
                app_module = sys.modules['app']
                if hasattr(app_module, 'db') and hasattr(app_module.db, 'engine'):
                    app_module.db.engine.dispose()
                    logger.warning("ULTRA: SQLAlchemy application connection pool disposed")
            
            # Find and dispose ALL SQLAlchemy engines anywhere in the system
            for module_name in list(sys.modules.keys()):
                try:
                    module = sys.modules[module_name]
                    for attr_name in dir(module):
                        try:
                            attr = getattr(module, attr_name)
                            # If it looks like an Engine object
                            if hasattr(attr, 'dispose') and callable(attr.dispose):
                                attr.dispose()
                                logger.debug(f"ULTRA: Disposed SQLAlchemy engine in {module_name}.{attr_name}")
                        except:
                            pass
                except:
                    pass
            
            # Find and close any Session objects
            for obj in gc.get_objects():
                try:
                    if 'sqlalchemy' in str(type(obj)) and hasattr(obj, 'close') and callable(obj.close):
                        obj.close()
                except:
                    pass
        except Exception as e:
            logger.warning(f"Failed to dispose SQLAlchemy connections: {str(e)}")
    
    # ----- PHASE 5: ULTRA-AGGRESSIVE GARBAGE COLLECTION -----
    
    # Run garbage collection multiple times through all generations
    gc.collect(generation=2)  # Gen 2 (oldest objects)
    gc.collect(generation=1)  # Gen 1 
    gc.collect(generation=0)  # Gen 0 (youngest objects)
    
    # Disable automatic garbage collection temporarily for manual control
    was_enabled = gc.isenabled()
    gc.disable()
    
    # Run unreachable object collection more aggressively
    gc.collect(generation=2)
    
    # Clear reference cycles by finding and breaking them
    try:
        # Get count of objects before clearing cycles
        objects_before = len(gc.get_objects())
        
        # Find and clear dictionaries to break cycles (more aggressive approach)
        dict_cleared = 0
        for obj in gc.get_objects():
            try:
                # Clear dictionaries (major source of reference cycles)
                if isinstance(obj, dict) and not hasattr(obj, '__dict__'):
                    obj.clear()
                    dict_cleared += 1
                # Clear lists that might hold references
                elif isinstance(obj, list) and len(obj) > 0:
                    obj.clear()
                # Clear sets that might hold references
                elif isinstance(obj, set) and len(obj) > 0:
                    obj.clear()
            except:
                pass
            
        # Log dictionary clearing
        if dict_cleared > 0:
            logger.warning(f"ULTRA: Cleared {dict_cleared} dictionaries to break reference cycles")
        
        # Find objects with __dict__ attributes and clear them if possible
        custom_obj_cleared = 0
        for obj in gc.get_objects():
            try:
                if hasattr(obj, '__dict__') and not isinstance(obj, type):
                    # Replace the __dict__ with an empty one to break cycles
                    obj.__dict__.clear()
                    custom_obj_cleared += 1
            except:
                pass
                
        # Log custom object clearing
        if custom_obj_cleared > 0:
            logger.warning(f"ULTRA: Cleared __dict__ of {custom_obj_cleared} custom objects")
        
        # Run another collection to clean up broken cycles
        gc.collect(generation=2)
        
        # Get count after to see if we made progress
        objects_after = len(gc.get_objects())
        if objects_before > objects_after:
            logger.warning(f"ULTRA: Cleared {objects_before - objects_after} objects through aggressive cycle breaking")
    except Exception as e:
        logger.warning(f"Error during aggressive reference cycle clearing: {str(e)}")
    
    # Run one final collection on all generations
    gc.collect(generation=2)
    gc.collect(generation=1)
    gc.collect(generation=0)
    
    # Restore previous GC state
    if was_enabled:
        gc.enable()
    
    # ----- PHASE 6: OS-LEVEL MEMORY TRIMMING -----
    
    # Try all available methods to return memory to the OS
    try:
        if sys.platform.startswith('linux'):
            # On Linux, use malloc_trim from the C library
            import ctypes
            try:
                libc = ctypes.CDLL('libc.so.6')
                # Call malloc_trim(0) which asks glibc to release free memory
                if hasattr(libc, 'malloc_trim'):
                    result = libc.malloc_trim(0)
                    logger.warning(f"ULTRA: Called malloc_trim(0) to release memory to OS: result={result}")
                    
                    # Call it again for good measure
                    libc.malloc_trim(0)
            except Exception as e:
                logger.warning(f"Failed to call malloc_trim: {str(e)}")
                
            # Try alternative method: Write to /proc/self/oom_score_adj
            try:
                # This tells the kernel this process can be killed earlier under memory pressure
                # It doesn't directly free memory but helps prioritize this process for OOM killing
                with open('/proc/self/oom_score_adj', 'w') as f:
                    f.write('500')  # Higher value (max 1000) means more likely to be killed under pressure
                logger.warning("ULTRA: Set higher OOM score to allow better memory management")
            except:
                pass
    except Exception as e:
        logger.warning(f"Failed to trim memory at OS level: {str(e)}")
    
    # ----- PHASE 7: FINAL MEASUREMENT AND REPORTING -----
    
    # Force one more garbage collection
    gc.collect(generation=2)
    
    # Get after stats
    after_mem = process.memory_info().rss / 1024 / 1024  # MB
    
    # Calculate memory reduction
    mem_freed = before_mem - after_mem
    
    if mem_freed > 0:
        logger.warning(f"ULTRA-AGGRESSIVE OPTIMIZATION COMPLETE - Memory now: {after_mem:.1f} MB (freed {mem_freed:.1f} MB, {(mem_freed/before_mem)*100:.1f}%)")
    else:
        logger.error(f"MEMORY OPTIMIZATION FAILED - Memory now: {after_mem:.1f} MB (increased by {-mem_freed:.1f} MB)")
    
    # Return memory statistics
    return {
        'before_mb': round(before_mem, 1),
        'after_mb': round(after_mem, 1),
        'saved_mb': round(mem_freed, 1),
        'saved_percent': round((mem_freed/before_mem)*100 if before_mem > 0 else 0, 1)
    }

def force_deep_sleep():
    """
    Force the background processor into deep sleep mode.
    This function immediately puts the background processor into deep sleep
    mode, which significantly reduces CPU and memory usage.
    
    Returns:
        bool: True if deep sleep mode was activated, False otherwise
    """
    global _background_processor
    
    if _background_processor is None:
        logger.warning("Background processor not initialized, cannot force deep sleep")
        return False
        
    try:
        logger.info("Manually forcing deep sleep mode via API request")
        
        # Set to extreme values to ensure persistent deep sleep
        _background_processor.consecutive_idle_cycles = _background_processor.deep_sleep_threshold * 2
        _background_processor.in_deep_sleep = True
        
        # Set a much longer sleep time for manual activation - 30 minutes
        _background_processor.sleep_time = _background_processor.deep_sleep_time * 3  # 30 minutes
        
        # Set a flag to indicate manual activation, which will prevent auto-exit
        _background_processor.manually_activated_sleep = True
        
        # Aggressively release memory and clear caches
        memory_stats = reduce_memory_usage()
        
        # Set ultra-aggressive cache parameters in deep sleep mode
        try:
            # Use safer dict-based access to modify module variables
            llm_service_module = _lazy_import('utils.llm_service')
            
            # Apply ULTRA-MINIMAL caching settings for absolute minimum memory usage
            if hasattr(llm_service_module, '_CACHE_TTL'):
                llm_service_module._CACHE_TTL = 1  # 1 second TTL (absolutely minimal)
            if hasattr(llm_service_module, '_CACHE_CLEANUP_INTERVAL'):
                llm_service_module._CACHE_CLEANUP_INTERVAL = 1  # Clean up every single second
            if hasattr(llm_service_module, '_MAX_CACHE_SIZE'):
                llm_service_module._MAX_CACHE_SIZE = 2  # Absolute minimal cache size (only 2 entries)
            if hasattr(llm_service_module, '_CACHE_MEMORY_LIMIT_MB'):
                llm_service_module._CACHE_MEMORY_LIMIT_MB = 0.5  # Ultra-minimal 0.5MB memory limit
                
            logger.warning(f"Set ULTRA-MINIMAL cache limits: TTL=1s, Cleanup=1s, Size=2, Memory=0.5MB")
        except Exception as e:
            logger.warning(f"Failed to update cache settings: {str(e)}")
        
        # Log detailed info about the sleep activation
        logger.info(f"Deep sleep mode activated manually. Sleep time set to {_background_processor.sleep_time}s")
        logger.info(f"Memory usage reduced by {memory_stats['saved_mb']}MB to {memory_stats['after_mb']}MB")
        
        # Pass 0.0 as rate when manually activating deep sleep
        resource_monitor = _lazy_import('utils.resource_monitor')
        resource_monitor.set_processing_status("deep_sleep", 0.0)
        return True
    except Exception as e:
        logger.error(f"Error forcing deep sleep mode: {str(e)}")
        return False

def exit_deep_sleep():
    """
    Exit deep sleep mode and reset to normal processing.
    This function is called when a new document is uploaded, to ensure it gets processed.
    
    Returns:
        bool: True if deep sleep mode was exited, False otherwise
    """
    global _background_processor
    
    if _background_processor is None:
        logger.warning("Background processor not initialized, cannot exit deep sleep")
        return False
        
    try:
        was_in_deep_sleep = False
        
        # Check if deep sleep was activated manually and create a clearer log message
        if _background_processor.manually_activated_sleep:
            logger.info("Exiting manually-activated deep sleep mode due to explicit user action")
            was_in_deep_sleep = True
        elif _background_processor.in_deep_sleep:
            logger.info("Exiting automatic deep sleep mode due to new document upload")
            was_in_deep_sleep = True
        else:
            # Already not in deep sleep
            return False
            
        # Reset all sleep-related flags regardless of how it was activated
        _background_processor.in_deep_sleep = False
        _background_processor.manually_activated_sleep = False
        _background_processor.consecutive_idle_cycles = 0
        _background_processor.sleep_time = _background_processor.base_sleep_time
        
        # Make sure vector store is loaded if it was unloaded
        if hasattr(_background_processor, 'vector_store_unloaded') and _background_processor.vector_store_unloaded:
            logger.info("Reloading vector store after deep sleep")
            _background_processor.ensure_vector_store_loaded()
        
        # Still run memory reduction for cleanup, but we expect it to be less effective
        # since we're about to start processing again
        memory_stats = reduce_memory_usage()
        
        # Reset cache settings to conservative values when exiting deep sleep
        try:
            # Use conservative values when exiting - don't go straight to full caching
            llm_service_module = _lazy_import('utils.llm_service')
            if hasattr(llm_service_module, '_CACHE_TTL'):
                llm_service_module._CACHE_TTL = 60  # 1 minute TTL (still conservative)
            if hasattr(llm_service_module, '_CACHE_CLEANUP_INTERVAL'):
                llm_service_module._CACHE_CLEANUP_INTERVAL = 30  # Clean up every 30 seconds
            if hasattr(llm_service_module, '_MAX_CACHE_SIZE'):
                llm_service_module._MAX_CACHE_SIZE = 25  # Small cache size when exiting deep sleep
            if hasattr(llm_service_module, '_CACHE_MEMORY_LIMIT_MB'):
                llm_service_module._CACHE_MEMORY_LIMIT_MB = 25  # 25MB memory limit (conservative)
                
            logger.warning(f"Reset cache to conservative settings: TTL=60s, Cleanup=30s, Size=25, Memory=25MB")
        except Exception as e:
            logger.warning(f"Failed to reset cache settings: {str(e)}")
        
        logger.info(f"Deep sleep mode exited. Sleep time reset to {_background_processor.sleep_time}s")
        logger.info(f"Memory status after exit: {memory_stats['after_mb']}MB (released {memory_stats['saved_mb']}MB)")
        
        # Reset status to active
        resource_monitor = _lazy_import('utils.resource_monitor')
        resource_monitor.set_processing_status("active", 0.0)
        return True
    except Exception as e:
        logger.error(f"Error exiting deep sleep mode: {str(e)}")
        return False
        
def is_in_deep_sleep():
    """
    Check if the background processor is currently in deep sleep mode.
    
    Returns:
        bool: True if the background processor is in deep sleep mode, False otherwise
    """
    global _background_processor
    
    if _background_processor is None:
        logger.warning("Background processor not initialized, cannot check deep sleep status")
        return False
        
    return _background_processor.in_deep_sleep

def get_processor_status():
    """
    Get the current status of the background processor for monitoring.
    
    Returns:
        dict: Status information about the background processor
    """
    global _background_processor
    
    if _background_processor is None:
        return {
            "status": "not_initialized",
            "in_deep_sleep": False,
            "vector_store_unloaded": True,
            "documents_processed": 0,
            "sleep_time": 0,
            "last_run_time": None
        }
    
    # Get status from the processor
    return {
        "status": "deep_sleep" if _background_processor.in_deep_sleep else "active",
        "in_deep_sleep": _background_processor.in_deep_sleep,
        "vector_store_unloaded": _background_processor.vector_store_unloaded,
        "documents_processed": _background_processor.documents_processed,
        "sleep_time": _background_processor.sleep_time,
        "last_run_time": _background_processor.last_run_time,
        "consecutive_idle_cycles": _background_processor.consecutive_idle_cycles,
        "deep_sleep_threshold": _background_processor.deep_sleep_threshold,
        "manually_activated_sleep": _background_processor.manually_activated_sleep
    }

def initialize_background_processor(batch_size=1, sleep_time=5):
    """
    Initialize and start the background processor.
    This function is called from main.py to start the background processor.
    
    Args:
        batch_size (int): Number of documents to process in each batch
        sleep_time (int): Time to sleep between batches in seconds
    
    Returns:
        BackgroundProcessor: The background processor instance
    """
    global _background_processor
    
    # If already initialized, just return the existing instance
    if _background_processor is not None:
        logger.info("Background processor already initialized")
        return _background_processor
    
    # Create a new background processor
    _background_processor = BackgroundProcessor(batch_size=batch_size, sleep_time=sleep_time)
    
    # Start the background processor
    _background_processor.start()
    
    return _background_processor

class BackgroundProcessor:
    """
    Background processor for handling document processing.
    Runs in a separate thread to process documents that haven't been processed yet.
    """
    def __init__(self, batch_size=1, sleep_time=5):
        """
        Initialize the background processor.
        
        Args:
            batch_size (int): Number of documents to process in each batch
            sleep_time (int): Time to sleep between batches in seconds
        """
        self.batch_size = batch_size
        self.base_sleep_time = sleep_time
        self.sleep_time = sleep_time  # Current sleep time (will adapt)
        self.max_sleep_time = 300     # Maximum sleep time (5 minutes)
        self.deep_sleep_time = 600    # Deep sleep mode (10 minutes)
        self.consecutive_idle_cycles = 10  # Start with enough idle cycles to trigger deep sleep
        self.deep_sleep_threshold = 10  # Cycles before entering deep sleep
        self.in_deep_sleep = True     # Start in deep sleep mode by default
        self.manually_activated_sleep = True   # Consider it manually activated at start
        self.running = False
        self.thread = None
        self.last_run_time = None
        self.documents_processed = 0
        self.last_work_found_time = time.time()  # Track when we last found work
        self.vector_store_unloaded = False  # Track if vector store has been unloaded
        
        # Lazily create SQLAlchemy engine and session
        sqlalchemy = _lazy_import('sqlalchemy')
        sqlalchemy_orm = _lazy_import('sqlalchemy.orm')
        self.engine = sqlalchemy.create_engine(DATABASE_URL)
        self.Session = sqlalchemy_orm.scoped_session(sqlalchemy_orm.sessionmaker(bind=self.engine))
        
        # Init vector store
        vector_store_module = _lazy_import('utils.vector_store')
        self.vector_store = vector_store_module.VectorStore()
        
        # Since we're starting in deep sleep mode, unload the vector store to save memory
        self.vector_store_unloaded = True
        logger.info("Starting in deep sleep mode with vector store unloaded")
        
    def ensure_vector_store_loaded(self):
        """
        Ensure the vector store is loaded in memory.
        If it was previously unloaded during deep sleep, reload it.
        
        Returns:
            bool: True if a reload was needed, False if already loaded
        """
        if self.vector_store_unloaded:
            logger.info("Vector store was unloaded, reloading from disk")
            docs_loaded = self.vector_store.reload_from_disk()
            logger.info(f"Reloaded {docs_loaded} documents into vector store")
            self.vector_store_unloaded = False
            return True
        return False
        
    def _create_session(self):
        """Create a new database session. Used to recover from transaction errors."""
        try:
            return self.Session()
        except Exception as e:
            logger.exception(f"Error creating session: {str(e)}")
            # If we can't create a session through the scoped session, try direct creation
            sqlalchemy_orm = _lazy_import('sqlalchemy.orm')
            return sqlalchemy_orm.sessionmaker(bind=self.engine)()
        
    def start(self, start_in_deep_sleep=True):
        """
        Start the background processor if it's not already running.
        
        Args:
            start_in_deep_sleep (bool): Whether to start in deep sleep mode to conserve resources
        """
        if self.running:
            logger.info("Background processor already running")
            return
        
        # Set deep sleep mode before starting if requested
        if start_in_deep_sleep:
            self.in_deep_sleep = True
            self.sleep_time = self.deep_sleep_time
            self.consecutive_idle_cycles = self.deep_sleep_threshold * 2
            logger.info("Starting in deep sleep mode with vector store unloaded")
            
            # Make sure vector store is unloaded to save memory at startup
            try:
                # Unload vector store to save memory
                self.vector_store.unload()
                self.vector_store_unloaded = True
            except Exception as e:
                logger.warning(f"Failed to unload vector store during startup: {str(e)}")
        
        self.running = True
        self.thread = threading.Thread(target=self._processing_loop)
        self.thread.daemon = True  # Thread will exit when main thread exits
        self.thread.start()
        logger.info("Background processor started")
        
    def stop(self):
        """Stop the background processor."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)  # Wait for thread to finish
            self.thread = None
        logger.info("Background processor stopped")
        
    def _processing_loop(self):
        """Main processing loop to find and process documents."""
        logger.info("Background processing loop started")
        
        while self.running:
            try:
                # Start a new session for this iteration
                session = self._create_session()
                
                # First, check if there are any processed website documents that have more content available
                # These are documents where file_size > 0 and file_size > number of chunks
                try:
                    # Find documents with more content to load
                    from sqlalchemy import func
                    subquery = session.query(
                        DocumentChunk.document_id,
                        func.count(DocumentChunk.id).label('chunk_count')
                    ).group_by(DocumentChunk.document_id).subquery()
                    
                    # Query for documents that:
                    # 1. Are website documents (since only websites support "load more")
                    # 2. Are already processed (so their initial content is available)
                    # 3. Have file_size > 0 (meaning they have more content available)
                    # 4. Have fewer chunks than file_size (the remaining content)
                    documents_with_more_content = session.query(Document).join(
                        subquery, 
                        Document.id == subquery.c.document_id
                    ).filter(
                        Document.file_type == 'website',
                        Document.processed == True,
                        Document.file_size > 0,
                        Document.file_size > subquery.c.chunk_count
                    ).limit(self.batch_size).all()
                    
                    if documents_with_more_content:
                        import urllib.parse
                        from utils.web_scraper import create_minimal_content_for_topic
                        
                        for doc in documents_with_more_content:
                            try:
                                logger.info(f"Loading more content for document {doc.id}: {doc.title}")
                                
                                # Get the current number of chunks
                                current_chunk_count = len(doc.chunks)
                                total_possible_chunks = doc.file_size or 0
                                
                                # Determine how many more chunks to load (maximum 100 at a time)
                                chunks_to_load = min(100, total_possible_chunks - current_chunk_count)
                                logger.info(f"Attempting to load {chunks_to_load} more chunks for document {doc.id}")
                                
                                # Get the document URL
                                url = doc.source_url
                                if not url:
                                    logger.warning(f"Document {doc.id} has no source URL, skipping")
                                    continue
                                
                                # Get fresh content to ensure we have all chunks
                                chunks = create_minimal_content_for_topic(url)
                                
                                if not chunks:
                                    logger.warning(f"Failed to retrieve additional content for document {doc.id}")
                                    continue
                                
                                # Skip chunks we already have and take only the next batch
                                start_index = current_chunk_count
                                end_index = min(start_index + chunks_to_load, len(chunks))
                                
                                if start_index >= len(chunks):
                                    logger.info(f"No additional content available for document {doc.id}")
                                    continue
                                
                                chunks_to_add = chunks[start_index:end_index]
                                added_count = 0
                                
                                # Process each additional chunk
                                for i, chunk in enumerate(chunks_to_add):
                                    try:
                                        # Update chunk index to continue from existing chunks
                                        chunk_index = current_chunk_count + i
                                        
                                        # Update metadata to reflect new chunk index
                                        chunk['metadata']['chunk_index'] = chunk_index
                                        
                                        # Add to vector store
                                        vector_store.add_text(chunk['text'], chunk['metadata'])
                                        
                                        # Create database record
                                        chunk_record = DocumentChunk(
                                            document_id=doc.id,
                                            chunk_index=chunk_index,
                                            page_number=chunk['metadata'].get('page_number', 1),
                                            text_content=chunk['text']
                                        )
                                        
                                        session.add(chunk_record)
                                        
                                        added_count += 1
                                    except Exception as e:
                                        logger.error(f"Error adding chunk {i+start_index}: {str(e)}")
                                
                                # Commit changes after processing all chunks for this document
                                session.commit()
                                vector_store._save()
                                
                                logger.info(f"Added {added_count} more chunks to document {doc.id}")
                                
                                # Update document if we've loaded all chunks
                                new_total = current_chunk_count + added_count
                                if new_total >= total_possible_chunks:
                                    logger.info(f"Document {doc.id} now has all {new_total} chunks loaded")
                                else:
                                    logger.info(f"Document {doc.id} now has {new_total}/{total_possible_chunks} chunks loaded")
                                
                                # Force Python garbage collection to free memory
                                import gc
                                gc.collect()
                                
                            except Exception as e:
                                logger.exception(f"Error loading additional content for document {doc.id}: {str(e)}")
                                session.rollback()
                                
                    # We processed some documents with more content, sleep before checking for unprocessed documents
                    if documents_with_more_content:
                        # Reset idle counter since we found work
                        self.consecutive_idle_cycles = 0
                        self.sleep_time = self.base_sleep_time  # Reset sleep time to base value
                        
                        logger.info(f"Processed {len(documents_with_more_content)} documents with more content, reset sleep time to {self.sleep_time}s")
                        time.sleep(self.sleep_time / 2)  # Sleep half the normal time before looking for unprocessed docs
                
                except Exception as e:
                    logger.exception(f"Error checking for documents with more content: {str(e)}")
                
                # Check for unprocessed documents
                try:
                    # First, look for documents with processing_state set (partially processed)
                    partially_processed_docs = []
                    try:
                        logger.debug("Checking for partially processed documents...")
                        partially_processed_docs = session.query(Document).filter(
                            Document.processed == False,
                            Document.processing_state.isnot(None)
                        ).limit(self.batch_size).all()
                        
                        if partially_processed_docs:
                            logger.info(f"Found {len(partially_processed_docs)} partially processed documents")
                    except Exception as e:
                        logger.warning(f"Error finding partially processed documents: {str(e)}")
                        # Close session and create a new one to recover from transaction errors
                        session.close()
                        session = self._create_session()
                    
                    # If no partially processed docs, look for any unprocessed docs
                    if not partially_processed_docs:
                        unprocessed_docs = session.query(Document).filter_by(
                            processed=False,
                        ).limit(self.batch_size).all()
                    else:
                        unprocessed_docs = partially_processed_docs
                    
                    if not unprocessed_docs:
                        # No work found, implement adaptive sleep time
                        self.consecutive_idle_cycles += 1
                        
                        # Periodically reduce memory even before deep sleep
                        if self.consecutive_idle_cycles > 5 and self.consecutive_idle_cycles % 5 == 0:
                            logger.info(f"Reducing memory after {self.consecutive_idle_cycles} idle cycles")
                            memory_stats = reduce_memory_usage()
                            logger.info(f"Memory usage reduced by {memory_stats['saved_mb']}MB to {memory_stats['after_mb']}MB")
                        
                        # Check if we should enter deep sleep mode
                        if self.consecutive_idle_cycles >= self.deep_sleep_threshold and not self.in_deep_sleep:
                            self.in_deep_sleep = True
                            self.sleep_time = self.deep_sleep_time
                            
                            # Reduce memory consumption when entering automatic deep sleep
                            memory_stats = reduce_memory_usage()
                            
                            # Also unload vector store from memory to significantly reduce memory usage
                            from utils.vector_store import vector_store
                            unloaded_docs = 0
                            if not self.vector_store_unloaded:
                                unloaded_docs = vector_store.unload()
                                self.vector_store_unloaded = True
                                logger.info(f"Unloaded vector store with {unloaded_docs} documents to save memory")
                            
                            logger.info(f"Entering deep sleep mode after {self.consecutive_idle_cycles} idle cycles, sleep time set to {self.deep_sleep_time}s")
                            logger.info(f"Memory usage reduced by {memory_stats['saved_mb']}MB to {memory_stats['after_mb']}MB")
                        # Otherwise use exponential backoff
                        elif not self.in_deep_sleep and self.consecutive_idle_cycles > 3:
                            # Double sleep time after 3 idle cycles (up to max limit)
                            self.sleep_time = min(self.sleep_time * 2, self.max_sleep_time)
                            logger.debug(f"No unprocessed documents found for {self.consecutive_idle_cycles} cycles, increasing sleep to {self.sleep_time}s")
                        elif self.in_deep_sleep:
                            logger.debug(f"In deep sleep mode, sleeping for {self.sleep_time}s")
                        else:
                            logger.debug(f"No unprocessed documents found, sleeping for {self.sleep_time}s...")
                            
                        session.close()
                        time.sleep(self.sleep_time)
                        continue
                        
                except Exception as e:
                    # Handle database transaction errors
                    logger.exception(f"Database error checking for unprocessed documents: {str(e)}")
                    # Close session and create a new one
                    try:
                        session.close()
                    except:
                        pass
                    time.sleep(2)  # Brief pause to let database recover
                    session = self._create_session()
                    continue
                
                # If manually activated sleep, we don't want to process work at all
                if self.manually_activated_sleep:
                    logger.info(f"Staying in deep sleep mode despite work (manually activated)")
                    
                    # Maintain high sleep time
                    self.sleep_time = max(self.sleep_time, self.deep_sleep_time * 3)
                    self.in_deep_sleep = True
                    
                    # Always reduce memory in manual sleep mode - reliable cleanup
                    # This is a guaranteed memory reduction even during manual sleep
                    memory_stats = reduce_memory_usage()
                    logger.info(f"Periodic memory cleanup during manual sleep: {memory_stats['saved_mb']}MB freed")
                    
                    # Skip processing - go straight to sleep
                    session.close()
                    time.sleep(self.sleep_time)
                    continue
                
                # If we got here, we have work to do, reset the idle counter and sleep time
                self.consecutive_idle_cycles = 0
                self.sleep_time = self.base_sleep_time  # Reset sleep time to base value
                
                # If we were in deep sleep, exit that mode (only happens for automatic deep sleep)
                if self.in_deep_sleep:
                    self.in_deep_sleep = False
                    logger.info(f"Exiting deep sleep mode, work found!")
                    
                    # Make sure to load the vector store if it was unloaded during deep sleep
                    if self.vector_store_unloaded:
                        self.ensure_vector_store_loaded()
                
                logger.debug(f"Found work to do, resetting sleep time to {self.sleep_time}s")
                
                # Process each document
                for doc in unprocessed_docs:
                    try:
                        logger.info(f"Background processing document {doc.id}: {doc.filename} (type: {doc.file_type})")
                        
                        # Handle PDF documents
                        if doc.file_type == 'pdf':
                            if not doc.file_path or not os.path.exists(doc.file_path):
                                logger.warning(f"File not found for document {doc.id}: {doc.file_path}")
                                doc.processed = True  # Mark as processed to skip it
                                session.commit()
                                continue
                                
                            # Process the PDF
                            chunks, metadata = process_pdf(doc.file_path, doc.filename)
                            from utils.pdf_parser import process_pdf_generator

                            chunks = []
                            metadata = None
                            
                            for i, (chunk, meta) in enumerate(process_pdf_generator(doc.file_path, doc.filename)):
                                chunks.append(chunk)
                                if metadata is None:
                                    metadata = meta  # Only set metadata once (it's the same for every yield)
                        
                        # Handle website documents
                        elif doc.file_type == 'website':
                            if not doc.source_url:
                                logger.warning(f"URL not found for document {doc.id}")
                                doc.processed = True  # Mark as processed to skip it
                                session.commit()
                                continue
                                
                            # Process the website
                            logger.info(f"Processing website: {doc.source_url}")
                            
                            # IMPORTANT: We're abandoning the multi-page approach completely
                            # Instead, we'll use a direct extraction approach for all websites that's optimized for maximum content
                            
                            # Always use the direct method now, bypassing the crawler
                            # This should produce more content chunks by focusing extraction efforts on a single page
                            from utils.web_scraper import extract_website_direct
                            logger.info(f"Using direct intensive extraction for website: {doc.source_url}")
                            
                            # Try the new direct extraction method
                            result = extract_website_direct(doc.source_url)
                            
                            # If the direct method fails or produces too little content, try the topic extraction as backup
                            if not result or len(result) < 5:
                                logger.info(f"Direct extraction produced insufficient content ({len(result) if result else 0} chunks), trying specialized extraction")
                                from utils.web_scraper import create_minimal_content_for_topic
                                result = create_minimal_content_for_topic(doc.source_url)
                                
                            # Log the result size
                            logger.info(f"Extracted {len(result) if result else 0} chunks from website")
                            
                            chunks = []
                            for i, chunk_data in enumerate(result):
                                chunks.append({
                                    'text': chunk_data['text'],
                                    'metadata': {
                                        'url': chunk_data.get('metadata', {}).get('url', doc.source_url),
                                        'page_number': i  # Use index as a pseudo-page number
                                    }
                                })
                            
                            metadata = {
                                'title': doc.title or "Website Document",
                                'source_url': doc.source_url
                            }
                        
                        if not chunks or not metadata:
                            logger.warning(f"No content extracted from document {doc.id}")
                            doc.processed = True  # Mark as processed to skip it in future
                            session.commit()
                            continue
                        
                        # Update document metadata
                        doc.title = metadata.get('title', doc.title)
                        doc.page_count = metadata.get('page_count', doc.page_count)
                        doc.doi = metadata.get('doi')
                        doc.authors = metadata.get('authors')
                        doc.journal = metadata.get('journal')
                        doc.publication_year = metadata.get('publication_year')
                        doc.volume = metadata.get('volume')
                        doc.issue = metadata.get('issue')
                        doc.pages = metadata.get('pages')
                        doc.formatted_citation = metadata.get('formatted_citation')
                        doc.processed = True
                        doc.updated_at = datetime.utcnow()
                        
                        # Add chunks to database and vector store
                        # Ensure the vector store is loaded before using it
                        if self.vector_store_unloaded:
                            self.ensure_vector_store_loaded()
                        
                        # Import vector store to use for adding chunks
                        from utils.vector_store import vector_store
                        
                        for i, chunk in enumerate(chunks):
                            # Create metadata for the chunk
                            chunk_metadata = {
                                'document_id': doc.id,
                                'chunk_index': i,
                                'page_number': chunk.get('metadata', {}).get('page_number', None),
                                'document_title': doc.title or doc.filename,
                                'file_type': doc.file_type,
                                'doi': doc.doi,
                                'formatted_citation': doc.formatted_citation,
                                'source_url': doc.source_url,
                                'citation': chunk.get('metadata', {}).get('citation', doc.formatted_citation)
                            }
                            
                            # Add to vector store
                            vector_store.add_text(chunk['text'], chunk_metadata)
                            
                            # Create database record
                            chunk_record = DocumentChunk(
                                document_id=doc.id,
                                chunk_index=i,
                                page_number=chunk.get('metadata', {}).get('page_number', None),
                                text_content=chunk['text']
                            )
                            
                            session.add(chunk_record)
                        
                        # Save changes
                        session.commit()
                        self.documents_processed += 1
                        self.last_run_time = datetime.utcnow()
                        logger.info(f"Successfully processed document {doc.id} with {len(chunks)} chunks")
                        
                    except Exception as e:
                        logger.exception(f"Error processing document {doc.id}: {str(e)}")
                        session.rollback()
                        # Mark as processed but with error flag (could add an error field to Document model)
                        try:
                            # Re-query the document to get a fresh instance
                            doc = session.query(Document).get(doc.id)
                            if doc:
                                doc.processed = True  # Mark as processed to avoid infinite retries
                                session.commit()
                        except Exception as commit_error:
                            logger.exception(f"Error updating document status: {str(commit_error)}")
                            session.rollback()
                
                # After processing batch, sleep before next iteration
                time.sleep(self.sleep_time)
                
            except Exception as e:
                logger.exception(f"Error in background processing loop: {str(e)}")
                time.sleep(self.sleep_time)  # Sleep to avoid tight error loop
                
            finally:
                # Always close the session
                session.close()
        
        logger.info("Background processing loop ended")
        
    def get_status(self):
        """Get the current status of the background processor with resource information."""
        # Lazily import resource monitor functions
        resource_monitor = _lazy_import('utils.resource_monitor')
        
        # Get current resource information
        resource_data = resource_monitor.get_resource_data()
        
        # Get system resources for real-time data
        system_resources = resource_monitor.get_system_resources()
        
        # Determine optimal processing mode based on resources
        proc_mode, batch_size, resource_limited = resource_monitor.determine_processing_mode(system_resources)
        
        # Count how many documents have more content to load
        session = None
        try:
            session = self._create_session()
            from sqlalchemy import func
            
            # Create subquery to get the chunk count for each document
            subquery = session.query(
                DocumentChunk.document_id,
                func.count(DocumentChunk.id).label('chunk_count')
            ).group_by(DocumentChunk.document_id).subquery()
            
            # Count documents waiting for more content loading
            waiting_documents = session.query(Document).join(
                subquery, 
                Document.id == subquery.c.document_id
            ).filter(
                Document.file_type == 'website',
                Document.processed == True,
                Document.file_size > 0,
                Document.file_size > subquery.c.chunk_count
            ).count()
            
            # Count documents waiting for initial processing
            unprocessed_documents = session.query(Document).filter_by(
                processed=False
            ).count()
            
            # Count total documents and chunks in database
            total_documents = session.query(Document).count()
            total_chunks = session.query(DocumentChunk).count()
            
            # Ensure vector store is loaded before using it
            if self.vector_store_unloaded:
                self.ensure_vector_store_loaded()
                
            # Count processed chunks in vector store
            processed_chunks = len(self.vector_store.get_processed_chunk_ids())
            
            # Calculate processing metrics
            processing_complete_percent = (processed_chunks / total_chunks * 100) if total_chunks > 0 else 0
            
            # Calculate estimated remaining time
            estimated_seconds_remaining = 0
            processing_rate = resource_data.get('processing_rate', 0)
            
            if processing_rate > 0:
                remaining_chunks = total_chunks - processed_chunks
                estimated_seconds_remaining = remaining_chunks / processing_rate
            
            # Format time for display
            if estimated_seconds_remaining > 0:
                minutes, seconds = divmod(int(estimated_seconds_remaining), 60)
                hours, minutes = divmod(minutes, 60)
                days, hours = divmod(hours, 24)
                
                if days > 0:
                    formatted_time = f"{days}d {hours}h {minutes}m"
                elif hours > 0:
                    formatted_time = f"{hours}h {minutes}m"
                else:
                    formatted_time = f"{minutes}m {seconds}s"
            else:
                formatted_time = "Unknown"
            
            if session:
                session.close()
        except Exception as e:
            logger.exception(f"Error getting document counts: {str(e)}")
            # Make sure we always close the session to prevent connection leaks
            if session:
                try:
                    session.rollback()  # Explicitly rollback any failed transactions
                    session.close()
                except Exception as session_error:
                    logger.exception(f"Error closing session: {str(session_error)}")
            
            waiting_documents = 0
            unprocessed_documents = 0
            total_documents = 0
            total_chunks = 0
            processed_chunks = 0
            processing_complete_percent = 0
            formatted_time = "Unknown"
        
        # Set current processing status in resource monitor
        current_mode = "idle"
        if self.running and unprocessed_documents > 0:
            current_mode = proc_mode
        
        # Respect deep sleep mode when set manually
        if self.in_deep_sleep:
            current_mode = "deep_sleep"
        
        # Lazily import resource monitor for setting status
        resource_monitor = _lazy_import('utils.resource_monitor')    
        resource_monitor.set_processing_status(current_mode, resource_data.get('processing_rate', 0))
        
        # Create status object with comprehensive information
        return {
            # Basic status
            'running': self.running and not self.in_deep_sleep,  # Show as not running when in deep sleep
            'last_run': self.last_run_time.isoformat() if self.last_run_time else None,
            'documents_processed': self.documents_processed,
            'unprocessed_documents': unprocessed_documents,
            'documents_waiting_for_more_content': waiting_documents,
            'current_sleep_time': self.sleep_time,
            'consecutive_idle_cycles': self.consecutive_idle_cycles,
            'in_deep_sleep': self.in_deep_sleep,
            'deep_sleep_threshold': self.deep_sleep_threshold,
            
            # Resource information
            'system_resources': {
                'cpu_percent': system_resources['cpu_percent'],
                'memory_percent': system_resources['memory_percent'],
                'memory_available_mb': system_resources['memory_available_mb'],
                'resource_limited': resource_limited
            },
            
            # Processing mode information
            'processing_mode': {
                'current_mode': current_mode,
                'recommended_mode': proc_mode,
                'recommended_batch_size': batch_size,
                'resource_constrained': resource_limited
            },
            
            # Processing progress metrics
            'processing_metrics': {
                'total_documents': total_documents,
                'total_chunks': total_chunks,
                'processed_chunks': processed_chunks,
                'percent_complete': round(processing_complete_percent, 1),
                'estimated_time_remaining': formatted_time,
                'processing_rate_chunks_per_second': round(resource_data.get('processing_rate', 0), 2)
            }
        }


# Use a single shared instance for the background processor
# This synchronizes _background_processor (for sleep control) with background_processor (for API usage)
_background_processor = BackgroundProcessor(batch_size=1, sleep_time=10)
background_processor = _background_processor

# Initialize both with the same instance to ensure sleep mode functions correctly
# and deep sleep state is properly reported through the API
