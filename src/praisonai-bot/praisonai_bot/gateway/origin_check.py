"""
Origin validation for WebSocket connections.

Provides Cross-Site WebSocket Hijacking (CSWSH) defense by validating
the Origin header against an allowed origins allowlist.

This is a security feature and lives in the wrapper layer.
"""

from __future__ import annotations

from typing import List, Optional

# One implementation, in core (G-21); re-exported so old imports keep working.
from praisonaiagents.gateway.protocols import is_loopback  # noqa: F401


def check_origin(origin: Optional[str], allowed_origins: List[str], bind_host: str) -> bool:
    """Check if the WebSocket origin is allowed.
    
    Args:
        origin: The Origin header value from the WebSocket request
        allowed_origins: List of allowed origins (may contain "*" wildcard)
        bind_host: The host the gateway is bound to
        
    Returns:
        True if origin is allowed, False otherwise
        
    Raises:
        ValueError: If allowed_origins is required but not provided for external bind
    """
    # Loopback binds are permissive - allow all origins
    if is_loopback(bind_host):
        return True
    
    # External binds require explicit allowed_origins
    if not allowed_origins:
        raise ValueError(
            "allowed_origins is required when binding to external interfaces. "
            "Set GATEWAY_ALLOWED_ORIGINS environment variable or configure allowed_origins in config."
        )
    
    # No origin header - reject
    if not origin:
        return False
    
    # Check if origin is in the allowlist or wildcard is present
    return origin in allowed_origins or "*" in allowed_origins


class GatewayStartupError(Exception):
    """Raised when gateway cannot start due to configuration issues."""
    pass