"""
Shared utilities for memory modules.

This module contains utility functions that were originally in memory.py
and are needed by the decomposed mixin modules.
"""

import os
import threading
import logging

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
            return True
        except ImportError:
            _module_cache["chromadb"] = {"available": False}
            return False

def _get_chromadb():
    """Thread-safe lazy import of chromadb (only if available)."""
    if "chromadb" not in _module_cache or not _module_cache["chromadb"]["available"]:
        if not _check_chromadb():
            return {}
    
    with _import_lock:
        return {
            "module": _module_cache["chromadb"]["module"],
            "settings": _module_cache["chromadb"]["settings"]
        }

def _check_pymongo():
    """Thread-safe lazy check for pymongo availability."""
    if "pymongo" in _module_cache:
        return _module_cache["pymongo"]["available"]
    
    with _import_lock:
        if "pymongo" in _module_cache:
            return _module_cache["pymongo"]["available"]
        
        try:
            import pymongo
            import motor.motor_asyncio
            _module_cache["pymongo"] = {
                "available": True,
                "MongoClient": pymongo.MongoClient,
                "AsyncIOMotorClient": motor.motor_asyncio.AsyncIOMotorClient
            }
            return True
        except ImportError:
            _module_cache["pymongo"] = {"available": False}
            return False

def _get_pymongo():
    """Thread-safe lazy import of pymongo (only if available)."""
    if "pymongo" not in _module_cache or not _module_cache["pymongo"]["available"]:
        if not _check_pymongo():
            return {}
    
    with _import_lock:
        return {
            "MongoClient": _module_cache["pymongo"]["MongoClient"],
            "AsyncIOMotorClient": _module_cache["pymongo"]["AsyncIOMotorClient"]
        }

def _check_openai():
    """Thread-safe lazy check for openai availability."""
    if "openai" in _module_cache:
        return _module_cache["openai"]["available"]
    
    with _import_lock:
        if "openai" in _module_cache:
            return _module_cache["openai"]["available"]
        
        try:
            import openai
            _module_cache["openai"] = {
                "available": True,
                "module": openai
            }
            return True
        except ImportError:
            _module_cache["openai"] = {"available": False}
            return False

def _get_openai():
    """Thread-safe lazy import of openai (only if available)."""
    if "openai" not in _module_cache or not _module_cache["openai"]["available"]:
        if not _check_openai():
            return None
    
    with _import_lock:
        return _module_cache["openai"]["module"]