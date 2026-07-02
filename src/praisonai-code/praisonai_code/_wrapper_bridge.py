"""Lazy optional access to the ``praisonai`` wrapper from ``praisonai-code``.

Agentic CLI modules use this for wrapper-only features (bots, gateway, training,
framework adapters). Standalone ``pip install praisonai-code`` works for terminal
agent commands; wrapper imports fail with a clear install hint.
"""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any, TypeVar

T = TypeVar("T")

_INSTALL_HINT = "Install the full wrapper: pip install praisonai"


def wrapper_available() -> bool:
    """Return True when the ``praisonai`` wrapper package is importable."""
    import importlib.util

    return importlib.util.find_spec("praisonai") is not None


def import_wrapper_module(name: str) -> ModuleType:
    """Import ``praisonai.*`` or raise with an install hint."""
    if not name.startswith("praisonai"):
        raise ValueError(f"Expected praisonai module name, got {name!r}")
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise ImportError(f"{name} requires the praisonai wrapper. {_INSTALL_HINT}") from exc


def get_wrapper_attr(module_name: str, attr: str) -> Any:
    """Import a wrapper module and return one attribute."""
    return getattr(import_wrapper_module(module_name), attr)


def optional_wrapper_attr(module_name: str, attr: str, default: T | None = None) -> Any | T | None:
    """Return a wrapper attribute when installed, else ``default``.

    Falls back to ``default`` when the wrapper package is missing (ImportError)
    or when an installed wrapper module lacks the requested attribute
    (AttributeError), so callers degrade gracefully in both cases.
    """
    if not wrapper_available():
        return default
    try:
        return get_wrapper_attr(module_name, attr)
    except (ImportError, AttributeError):
        return default
