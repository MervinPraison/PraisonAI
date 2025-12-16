"""
MCP Security Module.

This module provides security utilities for MCP transports,
implementing security best practices from MCP Protocol
Revision 2025-11-25.

Security features:
- Origin header validation (DNS rebinding prevention)
- Localhost binding recommendations
- Authentication header support
- Secure session ID generation
"""

import secrets
import base64
from typing import Optional, Dict, List, Set
from urllib.parse import urlparse
from dataclasses import dataclass, field


# Localhost addresses
LOCALHOST_ADDRESSES: Set[str] = {
    'localhost',
    '127.0.0.1',
    '::1',  # IPv6 localhost
}


def is_valid_origin(
    origin: Optional[str],
    allowed_origins: List[str],
    allow_missing: bool = False
) -> bool:
    """
    Validate Origin header against allowed origins.
    
    Per MCP spec, servers MUST validate the Origin header on all
    incoming connections to prevent DNS rebinding attacks.
    
    Args:
        origin: The Origin header value
        allowed_origins: List of allowed origin hosts
        allow_missing: Whether to allow missing Origin header
        
    Returns:
        True if origin is valid, False otherwise
    """
    if not origin:
        return allow_missing
    
    # Extract host from origin
    host = extract_origin_host(origin)
    if not host:
        return False
    
    # Check against allowed origins
    return host in allowed_origins


def extract_origin_host(origin: str) -> Optional[str]:
    """
    Extract the host from an Origin header value.
    
    Args:
        origin: Origin header value (e.g., "https://example.com:443")
        
    Returns:
        Host portion of the origin, or None if invalid
    """
    if not origin:
        return None
    
    try:
        parsed = urlparse(origin)
        return parsed.hostname
    except Exception:
        return None


def is_localhost_address(address: str) -> bool:
    """
    Check if an address is a localhost address.
    
    Args:
        address: IP address or hostname
        
    Returns:
        True if localhost, False otherwise
    """
    return address.lower() in LOCALHOST_ADDRESSES


def should_bind_localhost_only(is_local: bool = True) -> bool:
    """
    Determine if server should bind to localhost only.
    
    Per MCP spec, when running locally, servers SHOULD bind only
    to localhost (127.0.0.1) rather than all network interfaces.
    
    Args:
        is_local: Whether this is a local development server
        
    Returns:
        True if should bind to localhost only
    """
    return is_local


def is_potential_dns_rebinding(origin: str, server_host: str) -> bool:
    """
    Detect potential DNS rebinding attack.
    
    DNS rebinding occurs when an external origin tries to access
    a local server through DNS manipulation.
    
    Args:
        origin: The Origin header value
        server_host: The host the server is bound to
        
    Returns:
        True if potential DNS rebinding attempt
    """
    origin_host = extract_origin_host(origin)
    if not origin_host:
        return True  # Treat invalid origin as suspicious
    
    # If server is on localhost, only localhost origins are safe
    if is_localhost_address(server_host):
        return not is_localhost_address(origin_host)
    
    # For non-localhost servers, check if origin matches server
    return origin_host != server_host


def create_auth_header(
    credentials: str,
    auth_type: str = "bearer",
    header_name: str = "Authorization"
) -> Dict[str, str]:
    """
    Create an authentication header.
    
    Args:
        credentials: The credentials/token
        auth_type: Type of auth ("bearer", "basic", "custom")
        header_name: Custom header name (for auth_type="custom")
        
    Returns:
        Dictionary with authentication header
    """
    if auth_type.lower() == "bearer":
        return {"Authorization": f"Bearer {credentials}"}
    
    elif auth_type.lower() == "basic":
        # Base64 encode for Basic auth
        encoded = base64.b64encode(credentials.encode()).decode()
        return {"Authorization": f"Basic {encoded}"}
    
    elif auth_type.lower() == "custom":
        return {header_name: credentials}
    
    else:
        raise ValueError(f"Unknown auth_type: {auth_type}")


def validate_auth_header(headers: Dict[str, str]) -> bool:
    """
    Validate that authentication header is present.
    
    Args:
        headers: Request headers dictionary
        
    Returns:
        True if Authorization header is present
    """
    # Check for Authorization header (case-insensitive)
    for key in headers:
        if key.lower() == 'authorization':
            return bool(headers[key])
    return False


def generate_secure_session_id(length: int = 32) -> str:
    """
    Generate a cryptographically secure session ID.
    
    Per MCP spec, session IDs SHOULD be globally unique and
    cryptographically secure (e.g., securely generated UUID,
    JWT, or cryptographic hash).
    
    The ID MUST only contain visible ASCII characters (0x21-0x7E).
    
    Args:
        length: Desired length of session ID (minimum 32)
        
    Returns:
        Secure session ID string
    """
    # Ensure minimum length for security
    length = max(length, 32)
    
    # Use URL-safe base64 which only uses visible ASCII
    # Generate extra bytes to account for base64 expansion
    num_bytes = (length * 3) // 4 + 1
    random_bytes = secrets.token_bytes(num_bytes)
    
    # Encode to URL-safe base64 (uses A-Z, a-z, 0-9, -, _)
    session_id = base64.urlsafe_b64encode(random_bytes).decode()
    
    # Trim to desired length
    return session_id[:length]


@dataclass
class SecurityConfig:
    """
    Security configuration for MCP transports.
    
    This class holds security settings that can be applied
    to MCP server implementations.
    
    Attributes:
        validate_origin: Whether to validate Origin header
        allow_missing_origin: Whether to allow missing Origin
        allowed_origins: List of allowed origin hosts
        require_auth: Whether authentication is required
        bind_localhost_only: Whether to bind to localhost only
    """
    validate_origin: bool = True
    allow_missing_origin: bool = False
    allowed_origins: List[str] = field(default_factory=lambda: ["localhost", "127.0.0.1"])
    require_auth: bool = False
    bind_localhost_only: bool = True
    
    def is_origin_allowed(self, origin: Optional[str]) -> bool:
        """Check if an origin is allowed by this config."""
        if not self.validate_origin:
            return True
        return is_valid_origin(
            origin,
            self.allowed_origins,
            self.allow_missing_origin
        )
    
    def get_bind_address(self) -> str:
        """Get recommended bind address based on config."""
        return "127.0.0.1" if self.bind_localhost_only else "0.0.0.0"
