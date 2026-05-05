"""Subscription / OAuth auth for LLM providers.

Opt-in, zero-overhead. Lazy-loaded via __getattr__ so importing
praisonaiagents stays fast.
"""
from __future__ import annotations

__all__ = [
    "SubscriptionAuthProtocol",
    "SubscriptionCredentials",
    "register_subscription_provider",
    "list_subscription_providers",
    "resolve_subscription_credentials",
]


def __getattr__(name):
    if name in ("SubscriptionAuthProtocol", "SubscriptionCredentials"):
        from .protocols import SubscriptionAuthProtocol, SubscriptionCredentials
        return locals()[name]
    if name in ("register_subscription_provider", "list_subscription_providers", "resolve_subscription_credentials"):
        from .registry import (
            register_subscription_provider,
            list_subscription_providers,
            resolve_subscription_credentials,
        )
        return locals()[name]
    raise AttributeError(name)