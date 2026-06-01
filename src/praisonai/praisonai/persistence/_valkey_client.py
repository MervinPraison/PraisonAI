"""
Shared Valkey client factory.

Centralises GlideClientSync creation so that ValkeyStateStore,
ValkeyVectorKnowledgeStore, and ValkeyStorageAdapter all use the
same connection logic.
"""

from typing import Optional

try:
    from glide_sync import (
        GlideClient as GlideClientSync,
        GlideClientConfiguration,
        NodeAddress,
        ServerCredentials,
    )
except ImportError:
    GlideClientSync = None
    GlideClientConfiguration = NodeAddress = ServerCredentials = None

_MISSING_MSG = (
    "valkey-glide-sync is required for Valkey support. "
    "Install with: pip install 'praisonai[valkey]'"
)


def create_valkey_client(
    host: str = "localhost",
    port: int = 6379,
    password: Optional[str] = None,
    db: int = 0,
    client_name: Optional[str] = "praisonai_valkey_client",
):
    """Create and return a GlideClientSync instance."""
    if GlideClientSync is None:
        raise ImportError(_MISSING_MSG)
    addresses = [NodeAddress(host, port)]
    creds = ServerCredentials(password=password) if password else None
    
    # Build configuration, only include client_name if provided
    config_kwargs = {
        "addresses": addresses,
        "credentials": creds,
        "database_id": db,
    }
    if client_name is not None:
        config_kwargs["client_name"] = client_name
    
    config = GlideClientConfiguration(**config_kwargs)
    return GlideClientSync.create(config)
