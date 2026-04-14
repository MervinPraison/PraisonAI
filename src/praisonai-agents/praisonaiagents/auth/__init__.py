"""
Authentication & Authorization Protocols for PraisonAI Agents.

This package provides protocol-driven auth interfaces for the core SDK.
Implementations (JWT, OAuth, etc.) live in the platform package.

Quick start::

    from praisonaiagents.auth import AuthIdentity, AuthBackendProtocol

    class MyAuthBackend:
        async def authenticate(self, credentials):
            return AuthIdentity(id="user-1", type="user", roles=["owner"])

        async def authorize(self, identity, resource, action):
            return "owner" in identity.roles
"""

from .protocols import (
    AuthIdentity,
    AuthBackendProtocol,
    WorkspaceContextProtocol,
    AuthConfig,
)

__all__ = [
    "AuthIdentity",
    "AuthBackendProtocol",
    "WorkspaceContextProtocol",
    "AuthConfig",
]
