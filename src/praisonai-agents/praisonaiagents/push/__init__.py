"""Push client public surface.

Concrete implementations live in the `praisonai` wrapper. This module
re-exports them lazily so user code can keep importing from
``praisonaiagents.push``.
"""
from .models import ChannelMessage
from .protocols import PushTransportProtocol

_lazy_cache: dict = {}

_WRAPPER_MAP = {
    "PushClient":        ("praisonai.push",            "PushClient"),
    "WebSocketTransport": ("praisonai.push",           "WebSocketTransport"),
    "PollingTransport":   ("praisonai.push",           "PollingTransport"),
}

def __getattr__(name: str):
    if name in _lazy_cache:
        return _lazy_cache[name]
    if name in _WRAPPER_MAP:
        mod, attr = _WRAPPER_MAP[name]
        try:
            import importlib
            obj = getattr(importlib.import_module(mod), attr)
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
