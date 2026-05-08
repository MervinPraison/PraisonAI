"""Subscription-auth protocol — what every provider must implement."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, runtime_checkable


@dataclass
class SubscriptionCredentials:
    """Resolved credentials ready to inject into an LLM client."""
    api_key: str                            # access_token (or "" for SDK-default chains like AWS)
    base_url: str = ""                       # provider endpoint
    headers: Dict[str, str] = field(default_factory=dict)  # extra headers (UA, x-app, betas)
    auth_scheme: str = "bearer"              # "bearer" | "x-api-key" | "sdk-default"
    expires_at_ms: Optional[int] = None     # epoch ms; None = no expiry tracked
    source: str = ""                         # "claude-code-keychain", "codex-cli-file", etc.


@runtime_checkable
class SubscriptionAuthProtocol(Protocol):
    """Discover, refresh, and inject subscription credentials."""

    def resolve_credentials(self) -> SubscriptionCredentials:
        """Return current valid credentials, refreshing if expiring soon.

        Raises:
            AuthError: if no usable credentials can be resolved.
        """
        ...

    def refresh(self) -> SubscriptionCredentials:
        """Force a refresh and return the new credentials."""
        ...

    def headers_for(self, base_url: str, model: str) -> Dict[str, str]:
        """Provider-specific headers (UA, beta flags) keyed off endpoint/model."""
        ...


class AuthError(RuntimeError):
    """Raised when subscription credentials cannot be resolved."""