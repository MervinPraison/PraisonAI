"""Lazy access to ``praisonai-browser`` from ``praisonai-code``."""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any, TypeVar

T = TypeVar("T")

_INSTALL_HINT = "Install the browser package: pip install praisonai-browser"


def browser_package_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("praisonai_browser") is not None


def import_browser_module(name: str) -> ModuleType:
    if not name.startswith("praisonai_browser"):
        raise ValueError(f"Expected praisonai_browser module name, got {name!r}")
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise ImportError(f"{name} requires praisonai-browser. {_INSTALL_HINT}") from exc


def optional_browser_attr(module_name: str, attr: str, default: T | None = None) -> Any | T | None:
    if not browser_package_available():
        return default
    try:
        return getattr(import_browser_module(module_name), attr)
    except (ImportError, AttributeError):
        return default
