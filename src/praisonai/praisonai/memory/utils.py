"""
Utility functions for memory implementations.

Thread-safe lazy loading and helper functions for database connections.
"""

import threading

# Thread-safe import cache
_import_lock = threading.Lock()
_module_cache = {}

def _check_chromadb():
    """Thread-safe lazy check for chromadb availability."""
    if "chromadb" in _module_cache:
        return _module_cache["chromadb"]["available"]
    
    with _import_lock:
        if "chromadb" in _module_cache:
            return _module_cache["chromadb"]["available"]
        
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            _module_cache["chromadb"] = {
                "available": True,
                "module": chromadb,
                "settings": ChromaSettings
            }
        except ImportError:
            _module_cache["chromadb"] = {"available": False}
        
        return _module_cache["chromadb"]["available"]

def _get_chromadb():
    """Get chromadb module and settings (thread-safe lazy load)."""
    if not _check_chromadb():
        raise ImportError("chromadb is required. Install with: pip install chromadb")
    return _module_cache["chromadb"]["module"], _module_cache["chromadb"]["settings"]

def _check_pymongo():
    """Thread-safe lazy check for pymongo availability."""
    if "pymongo" in _module_cache:
        return _module_cache["pymongo"]["available"]
    
    with _import_lock:
        if "pymongo" in _module_cache:
            return _module_cache["pymongo"]["available"]
        
        try:
            import pymongo
            from pymongo import MongoClient
            _module_cache["pymongo"] = {
                "available": True,
                "module": pymongo,
                "client": MongoClient
            }
        except ImportError:
            _module_cache["pymongo"] = {"available": False}
        
        return _module_cache["pymongo"]["available"]

def _get_pymongo():
    """Get pymongo module and MongoClient (thread-safe lazy load)."""
    if not _check_pymongo():
        raise ImportError("pymongo is required. Install with: pip install pymongo")
    return _module_cache["pymongo"]["module"], _module_cache["pymongo"]["client"]