"""Protocols package for PraisonAI Agents tools.

Contains lightweight protocol definitions and dataclasses.
Heavy implementations live in the wrapper package.
"""

from .tool_protocol import (
    ToolProtocol,
    CallableToolProtocol,
    AsyncToolProtocol,
    ValidatableToolProtocol,
)

# Lazy import to avoid loading protocols unless needed
def __getattr__(name: str):
    if name == "browser":
        from . import browser
        return browser
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "browser",
    "ToolProtocol",
    "CallableToolProtocol",
    "AsyncToolProtocol",
    "ValidatableToolProtocol",
]

