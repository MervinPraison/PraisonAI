"""Thread-safe provider registry for subscription auth."""
from __future__ import annotations

import threading
from typing import Callable, Dict, List, Optional

from .protocols import AuthError, SubscriptionAuthProtocol, SubscriptionCredentials

_REGISTRY: Dict[str, Callable[[], SubscriptionAuthProtocol]] = {}
_LOCK = threading.RLock()
_BUILTIN_REGISTERED = False


def register_subscription_provider(
    provider_id: str,
    factory: Callable[[], SubscriptionAuthProtocol],
) -> None:
    """Register a new subscription-auth provider.

    Args:
        provider_id: short id e.g. "claude-code", "codex", "gemini-cli".
        factory: zero-arg callable returning a SubscriptionAuthProtocol impl.
    """
    with _LOCK:
        _REGISTRY[provider_id] = factory


def list_subscription_providers() -> List[str]:
    _ensure_builtins()
    with _LOCK:
        return sorted(_REGISTRY)


def resolve_subscription_credentials(provider_id: str) -> SubscriptionCredentials:
    """Look up provider by id and resolve its credentials."""
    _ensure_builtins()
    with _LOCK:
        factory = _REGISTRY.get(provider_id)
    if factory is None:
        raise AuthError(
            f"Unknown subscription provider {provider_id!r}. "
            f"Registered: {list_subscription_providers()}"
        )
    return factory().resolve_credentials()


def get_subscription_provider(provider_id: str) -> Optional[SubscriptionAuthProtocol]:
    """Return a new provider instance for *provider_id*, or None if not registered."""
    _ensure_builtins()
    with _LOCK:
        factory = _REGISTRY.get(provider_id)
    return factory() if factory is not None else None


def _ensure_builtins() -> None:
    """Lazy register built-in providers on first use."""
    global _BUILTIN_REGISTERED
    with _LOCK:
        if _BUILTIN_REGISTERED:
            return
        _BUILTIN_REGISTERED = True

    from . import claude_code, codex, gemini_cli, qwen_cli   # noqa: F401
    # Each module registers itself at import time.