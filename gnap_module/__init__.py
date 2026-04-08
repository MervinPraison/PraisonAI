"""
GNAP (Git-Native Agent Protocol) Storage Plugin for PraisonAI Tools.

This module provides a storage backend that implements StorageBackendProtocol
using git repositories for durable task persistence and distributed coordination.

Key Features:
- Zero-server architecture using git
- Durable task queuing with .gnap folders  
- Multi-agent coordination via shared repositories
- Complete audit trail through git history
- Compatible with existing PraisonAI storage patterns

Usage:
    ```python
    from praisonai_tools.gnap import GNAPStorageBackend
    
    backend = GNAPStorageBackend(repo_path="./my_project")
    backend.save("task_123", {"status": "pending", "data": "..."})
    ```
"""

from .storage_backend import GNAPStorageBackend, get_gnap_backend, register_gnap_backend

__version__ = "1.0.0"
__author__ = "PraisonAI Team"

__all__ = [
    "GNAPStorageBackend", 
    "get_gnap_backend",
    "register_gnap_backend"
]