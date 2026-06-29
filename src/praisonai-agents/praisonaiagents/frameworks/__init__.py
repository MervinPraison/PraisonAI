"""Framework adapter protocols and shared helpers (no third-party framework deps)."""

from typing import TYPE_CHECKING

__all__ = [
    "FrameworkAdapterProtocol",
    "BaseFrameworkAdapter",
]

if TYPE_CHECKING:
    from .protocols import FrameworkAdapterProtocol
    from .base import BaseFrameworkAdapter


def __getattr__(name: str):
    if name == "FrameworkAdapterProtocol":
        from .protocols import FrameworkAdapterProtocol
        return FrameworkAdapterProtocol
    if name == "BaseFrameworkAdapter":
        from .base import BaseFrameworkAdapter
        return BaseFrameworkAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
