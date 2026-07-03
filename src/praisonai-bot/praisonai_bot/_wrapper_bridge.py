"""Lazy access from praisonai-bot to optional praisonai wrapper modules."""

from __future__ import annotations

import importlib
from typing import Any, Optional


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


def optional_wrapper_attr(module: str, attr: str, default: Any = None) -> Any:
    try:
        mod = import_wrapper_module(module)
        return getattr(mod, attr)
    except ImportError:
        return default
