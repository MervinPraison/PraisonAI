"""Push client public surface.

Concrete implementations live in the `praisonai` wrapper. This module
re-exports them lazily so user code can keep importing from
``praisonaiagents.push``.
"""
import importlib

from .models import ChannelMessage
from .protocols import PushTransportProtocol

_lazy_cache: dict = {}

_WRAPPER_MODULE = "praisonai.push"
_WRAPPER_NAMES = frozenset({"PushClient", "WebSocketTransport", "PollingTransport"})

def __getattr__(name: str):
    if name in _lazy_cache:
        return _lazy_cache[name]
    if name in _WRAPPER_NAMES:
        try:
            obj = getattr(importlib.import_module(_WRAPPER_MODULE), name)
        except ImportError as e:
            raise ImportError(
                f"{name} requires the praisonai wrapper package. "
                "Install with: pip install praisonai"
            ) from e
        _lazy_cache[name] = obj
        return obj
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ChannelMessage",
    "PushTransportProtocol",
    "PushClient",
    "WebSocketTransport",
    "PollingTransport",
]
