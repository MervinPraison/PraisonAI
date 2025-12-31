"""
Chainlit compatibility shim for PraisonAI.

This module provides forward/backward compatible imports for Chainlit internals
that may change between versions. It handles:
- EXPIRY_TIME / storage_expiry_time constant (renamed/removed in various versions)
- BaseStorageClient class location (moved from storage_clients.base to data.base)
- BaseDataLayer abstract methods (close() added in 2.9.4, may be removed later)

Usage:
    from praisonai.ui.chainlit_compat import get_expiry_seconds, BaseStorageClient
"""

import os
from typing import Optional, Type

# Default expiry time in seconds (1 hour) - used if Chainlit doesn't provide one
DEFAULT_EXPIRY_SECONDS = 3600


def get_expiry_seconds() -> int:
    """
    Get the storage expiry time in seconds.
    
    Tries to retrieve from Chainlit's configuration in a version-compatible way.
    Falls back to DEFAULT_EXPIRY_SECONDS if not available.
    
    Returns:
        int: Expiry time in seconds
    """
    # First check environment variable (highest priority)
    env_expiry = os.getenv("STORAGE_EXPIRY_TIME")
    if env_expiry is not None:
        try:
            return int(env_expiry)
        except ValueError:
            pass
    
    # Try to import from Chainlit (version-compatible)
    # Try multiple known locations across Chainlit versions
    
    # Chainlit 2.9.x: storage_expiry_time in storage_clients.base
    try:
        from chainlit.data.storage_clients.base import storage_expiry_time
        return storage_expiry_time
    except ImportError:
        pass
    
    # Older versions: EXPIRY_TIME (uppercase) in storage_clients.base
    try:
        from chainlit.data.storage_clients.base import EXPIRY_TIME
        return EXPIRY_TIME
    except ImportError:
        pass
    
    # Fallback to default
    return DEFAULT_EXPIRY_SECONDS


def get_base_storage_client() -> Optional[Type]:
    """
    Get the BaseStorageClient class from Chainlit.
    
    Handles multiple import locations across Chainlit versions:
    - chainlit.data.base (latest/development)
    - chainlit.data.storage_clients.base (2.9.x)
    
    Returns:
        Type: BaseStorageClient class, or None if not available
    """
    # Try latest location first (chainlit.data.base)
    try:
        from chainlit.data.base import BaseStorageClient
        return BaseStorageClient
    except ImportError:
        pass
    
    # Try 2.9.x location
    try:
        from chainlit.data.storage_clients.base import BaseStorageClient
        return BaseStorageClient
    except ImportError:
        pass
    
    return None


def get_base_data_layer() -> Optional[Type]:
    """
    Get the BaseDataLayer class from Chainlit.
    
    Returns:
        Type: BaseDataLayer class, or None if not available
    """
    try:
        from chainlit.data.base import BaseDataLayer
        return BaseDataLayer
    except ImportError:
        pass
    
    try:
        from chainlit.data import BaseDataLayer
        return BaseDataLayer
    except ImportError:
        pass
    
    return None


def base_data_layer_has_close() -> bool:
    """
    Check if BaseDataLayer has a close() method.
    
    This method was added in Chainlit 2.9.4 but may be removed in future versions.
    
    Returns:
        bool: True if close() method exists, False otherwise
    """
    base_class = get_base_data_layer()
    if base_class is None:
        return False
    
    import inspect
    # Check if close is an abstract method or regular method
    for name, method in inspect.getmembers(base_class):
        if name == 'close':
            return True
    return False


# For backward compatibility, expose EXPIRY_TIME as an alias
# This allows existing code to import it without changes
EXPIRY_TIME = get_expiry_seconds()

# Re-export BaseStorageClient for convenience
# Try multiple locations for compatibility
BaseStorageClient = None
try:
    from chainlit.data.base import BaseStorageClient
except ImportError:
    try:
        from chainlit.data.storage_clients.base import BaseStorageClient
    except ImportError:
        BaseStorageClient = None


__all__ = [
    'get_expiry_seconds',
    'get_base_storage_client',
    'get_base_data_layer',
    'base_data_layer_has_close',
    'EXPIRY_TIME',
    'BaseStorageClient',
    'DEFAULT_EXPIRY_SECONDS',
]
