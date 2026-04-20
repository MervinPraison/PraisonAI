"""
Push notification client module for PraisonAI Agents.

Provides a Python SDK for consuming push notifications from
the PraisonAI gateway's push service.

This module uses lazy loading to avoid importing heavy dependencies
(websockets, aiohttp) until actually needed.
"""

from .models import ChannelMessage

# Lazy loading cache
_lazy_cache = {}


def __getattr__(name: str):
    """Lazy load PushClient and transports."""
    if name in _lazy_cache:
        return _lazy_cache[name]

    if name == "PushClient":
        from .client import PushClient
        _lazy_cache[name] = PushClient
        return PushClient

    if name == "WebSocketTransport":
        from .transports import WebSocketTransport
        _lazy_cache[name] = WebSocketTransport
        return WebSocketTransport

    if name == "PollingTransport":
        from .transports import PollingTransport
        _lazy_cache[name] = PollingTransport
        return PollingTransport

    if name == "PushTransportProtocol":
        from .transports import PushTransportProtocol
        _lazy_cache[name] = PushTransportProtocol
        return PushTransportProtocol

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "PushClient",
    "ChannelMessage",
    "WebSocketTransport",
    "PollingTransport",
    "PushTransportProtocol",
]
