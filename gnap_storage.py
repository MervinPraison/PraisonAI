"""
GNAP Storage Backend Implementation.

Standalone storage backend that can be used independently of the plugin system.
"""

from .gnap_plugin import GnapPlugin


class GNAPStorageBackend(GnapPlugin):
    """
    Standalone GNAP storage backend.
    
    This is an alias to GnapPlugin for users who want to use GNAP
    as a storage backend without the plugin system.
    
    Usage:
        from praisonai_tools.plugins.gnap import GNAPStorageBackend
        
        backend = GNAPStorageBackend(repo_path="./my_project")
        backend.save("task_123", {"status": "pending"})
        task = backend.load("task_123")
    """
    pass


# Factory function for entry points
def get_gnap_backend():
    """Factory function for storage backend entry points."""
    return GNAPStorageBackend