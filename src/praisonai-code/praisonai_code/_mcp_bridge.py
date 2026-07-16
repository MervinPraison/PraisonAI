"""Lazy access to ``praisonai-mcp`` from ``praisonai-code``."""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any, TypeVar

T = TypeVar("T")

_INSTALL_HINT = "Install the MCP package: pip install praisonai-mcp"


def mcp_package_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("praisonai_mcp") is not None


def import_mcp_module(name: str) -> ModuleType:
    if not name.startswith("praisonai_mcp"):
        raise ValueError(f"Expected praisonai_mcp module name, got {name!r}")
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise ImportError(f"{name} requires praisonai-mcp. {_INSTALL_HINT}") from exc


def optional_mcp_attr(module_name: str, attr: str, default: T | None = None) -> Any | T | None:
    if not mcp_package_available():
        return default
    try:
        return getattr(import_mcp_module(module_name), attr)
    except (ImportError, AttributeError):
        return default
