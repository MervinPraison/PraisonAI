"""CLI backend helpers for hooks and observability."""

from __future__ import annotations

from typing import Any


def backend_label(backend: Any) -> str:
    """Human-readable backend identifier for hooks and logs."""
    config = getattr(backend, "config", None)
    command = getattr(config, "command", None)
    if command:
        return str(command)
    return type(backend).__name__
