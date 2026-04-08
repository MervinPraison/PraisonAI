"""
GNAP (Git-Native Agent Persistence) Plugin for PraisonAI Tools.

This plugin provides git-native task persistence for distributed multi-agent workflows.
It implements the StorageBackendProtocol and PluginProtocol for seamless integration.

Features:
- Git-native task persistence with automatic commits
- Distributed coordination via shared repositories
- Branch-based workflow isolation
- Crash recovery and state restoration
- Zero-server architecture (no Redis/Celery required)

Usage:
    from praisonai_tools.plugins.gnap import GnapPlugin
    
    # As a plugin
    plugin = GnapPlugin(repo_path="./my_project")
    
    # As a storage backend
    backend = plugin.get_storage_backend()
    backend.save("task_123", {"status": "completed"})
"""

from .gnap_plugin import GnapPlugin
from .storage import GNAPStorageBackend
from .tools import gnap_save_state, gnap_load_state, gnap_list_tasks, gnap_commit

__all__ = [
    'GnapPlugin',
    'GNAPStorageBackend', 
    'gnap_save_state',
    'gnap_load_state',
    'gnap_list_tasks', 
    'gnap_commit'
]

# Plugin factory function for entry points registration
def get_gnap_plugin():
    """Factory function for entry points registration."""
    return GnapPlugin