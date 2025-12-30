"""
MCP Authentication and Authorization Module

Implements OAuth 2.1 and OpenID Connect support per MCP 2025-11-25 specification.

Features:
- API Key authentication
- OAuth 2.1 authorization framework
- OpenID Connect Discovery
- Client ID Metadata Documents
- Incremental scope handling
- WWW-Authenticate challenges
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .oauth import OAuthConfig, OAuthManager
    from .oidc import OIDCDiscovery, OIDCConfig
    from .api_key import APIKeyAuth
    from .scopes import ScopeManager, ScopeChallenge

__all__ = [
    "OAuthConfig",
    "OAuthManager",
    "OIDCDiscovery",
    "OIDCConfig",
    "APIKeyAuth",
    "ScopeManager",
    "ScopeChallenge",
]


def __getattr__(name: str):
    """Lazy load auth components."""
    if name in ("OAuthConfig", "OAuthManager"):
        from .oauth import OAuthConfig, OAuthManager
        return OAuthConfig if name == "OAuthConfig" else OAuthManager
    elif name in ("OIDCDiscovery", "OIDCConfig"):
        from .oidc import OIDCDiscovery, OIDCConfig
        return OIDCDiscovery if name == "OIDCDiscovery" else OIDCConfig
    elif name == "APIKeyAuth":
        from .api_key import APIKeyAuth
        return APIKeyAuth
    elif name in ("ScopeManager", "ScopeChallenge"):
        from .scopes import ScopeManager, ScopeChallenge
        return ScopeManager if name == "ScopeManager" else ScopeChallenge
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
