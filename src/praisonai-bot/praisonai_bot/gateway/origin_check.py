"""
Origin validation for WebSocket connections.

Provides Cross-Site WebSocket Hijacking (CSWSH) defense by validating
the Origin header against an allowed origins allowlist.

This is a security feature and lives in the wrapper layer.
"""

from __future__ import annotations

import ipaddress
from typing import List, Optional


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


def is_loopback(host: str) -> bool:
    """Check if a host is a loopback address.
    
    Args:
        host: The host address to check
        
    Returns:
        True if the host is a loopback address, False otherwise
    """
    if not host:
        return False
    
    # Check common loopback names
    if host in ("localhost", "127.0.0.1", "::1"):
        return True
    
    try:
        # Parse as IP address and check if it's loopback
        ip = ipaddress.ip_address(host)
        return ip.is_loopback
    except ValueError:
        # Not a valid IP address - assume it's a hostname
        # Only localhost is considered loopback for hostnames
        return host == "localhost"


class GatewayStartupError(Exception):
    """Raised when gateway cannot start due to configuration issues."""
    pass