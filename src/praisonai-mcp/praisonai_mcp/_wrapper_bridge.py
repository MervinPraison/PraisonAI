"""Lazy access from praisonai-mcp to optional praisonai wrapper modules."""

from __future__ import annotations

import importlib
from typing import Any, Callable


def wrapper_available() -> bool:
    try:
        import praisonai  # noqa: F401
        return True
    except ImportError:
        return False


def import_wrapper_module(name: str) -> Any:
    if not wrapper_available():
        raise ImportError(
            f"Optional wrapper module {name!r} requires the praisonai package. "
            "Install with: pip install praisonai"
        )
    return importlib.import_module(name)


def wrapper_callable(module: str, attr: str) -> Callable[..., Any]:
    return getattr(import_wrapper_module(module), attr)


def optional_wrapper_callable(
    module: str, attr: str, default: Callable[..., Any] | None = None
) -> Callable[..., Any] | None:
    try:
        return wrapper_callable(module, attr)
    except ImportError:
        return default
