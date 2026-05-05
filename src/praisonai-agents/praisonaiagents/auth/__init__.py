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

Subscription auth (lazy-loaded)::

    from praisonaiagents.auth import resolve_subscription_credentials
    
    creds = resolve_subscription_credentials("claude-code")
    print(creds.api_key, creds.headers)
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
    # Subscription auth (lazy-loaded)
    "SubscriptionAuthProtocol",
    "SubscriptionCredentials",
    "register_subscription_provider",
    "list_subscription_providers",
    "resolve_subscription_credentials",
    "get_subscription_provider",
]


def __getattr__(name):
    """Lazy-load subscription auth to avoid import overhead."""
    if name in (
        "SubscriptionAuthProtocol", 
        "SubscriptionCredentials",
        "register_subscription_provider",
        "list_subscription_providers", 
        "resolve_subscription_credentials",
        "get_subscription_provider",
    ):
        from .subscription import (
            SubscriptionAuthProtocol,
            SubscriptionCredentials,
            register_subscription_provider,
            list_subscription_providers,
            resolve_subscription_credentials,
            get_subscription_provider,
        )
        return locals()[name]
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
