"""
PraisonAI Agents Storage Framework.

Provides common storage abstractions for JSON-based persistence with:
- Thread-safe operations
- File locking for concurrent access
- Common session info dataclass

Zero performance impact when not in use through lazy loading.

Example:
    >>> from praisonaiagents.storage import BaseJSONStore, BaseSessionInfo
    >>> class MyStore(BaseJSONStore):
    ...     pass
"""

__all__ = [
    "BaseJSONStore",
    "AsyncBaseJSONStore",
    "BaseSessionInfo",
    "JSONStoreProtocol",
    "SessionInfoProtocol",
    "StorageBackendProtocol",
    "AsyncStorageBackendProtocol",
    "FileLock",
    "list_json_sessions",
    "cleanup_old_sessions",
    # Backend implementations
    "FileBackend",
    "SQLiteBackend",
    "RedisBackend",
    "get_backend",
]

_LAZY_IMPORTS = {
    "BaseJSONStore": ("base", "BaseJSONStore"),
    "BaseSessionInfo": ("models", "BaseSessionInfo"),
    "JSONStoreProtocol": ("protocols", "JSONStoreProtocol"),
    "SessionInfoProtocol": ("protocols", "SessionInfoProtocol"),
    "StorageBackendProtocol": ("protocols", "StorageBackendProtocol"),
    "AsyncStorageBackendProtocol": ("protocols", "AsyncStorageBackendProtocol"),
    "FileLock": ("base", "FileLock"),
    "AsyncBaseJSONStore": ("base", "AsyncBaseJSONStore"),
    "list_json_sessions": ("base", "list_json_sessions"),
    "cleanup_old_sessions": ("base", "cleanup_old_sessions"),
    # Backend implementations
    "FileBackend": ("backends", "FileBackend"),
    "SQLiteBackend": ("backends", "SQLiteBackend"),
    "RedisBackend": ("backends", "RedisBackend"),
    "get_backend": ("backends", "get_backend"),
}


def __getattr__(name: str):
    """Lazy import mechanism for zero-cost imports when not used."""
    if name in _LAZY_IMPORTS:
        module_name, attr_name = _LAZY_IMPORTS[name]
        import importlib
        module = importlib.import_module(f".{module_name}", __name__)
        return getattr(module, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    """Return list of available attributes for tab completion."""
    return __all__
