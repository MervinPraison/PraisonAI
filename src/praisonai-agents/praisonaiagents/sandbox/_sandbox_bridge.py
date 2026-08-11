"""Lazy access to praisonai-sandbox from praisonaiagents."""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any, TypeVar

T = TypeVar("T")

_INSTALL_HINT = "Install sandbox backends: pip install praisonai-sandbox"

_EXTRA_HINTS = {
    "docker": "pip install praisonai-sandbox[docker]",
    "e2b": "pip install praisonai-sandbox[e2b]",
    "sandlock": "pip install praisonai-sandbox[sandlock]",
    "ssh": "pip install praisonai-sandbox[ssh]",
    "modal": "pip install praisonai-sandbox[modal]",
    "daytona": "pip install praisonai-sandbox[daytona]",
}


def sandbox_package_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("praisonai_sandbox") is not None


def import_sandbox_module(name: str) -> ModuleType:
    if not name.startswith("praisonai_sandbox"):
        raise ValueError(f"Expected praisonai_sandbox module name, got {name!r}")
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise ImportError(f"{name} requires praisonai-sandbox. {_INSTALL_HINT}") from exc


def get_sandbox_registry():
    """Return the SandboxRegistry class from praisonai-sandbox (or legacy shim)."""
    if sandbox_package_available():
        return import_sandbox_module("praisonai_sandbox._registry").SandboxRegistry
    try:
        return importlib.import_module("praisonai.sandbox._registry").SandboxRegistry
    except ImportError as exc:
        raise ImportError(
            f"Sandbox backends not available. {_INSTALL_HINT}"
        ) from exc


def resolve_sandbox_class(name: str) -> type:
    """Resolve a sandbox implementation class by type name."""
    registry_cls = get_sandbox_registry()
    registry = registry_cls.default()
    return registry.resolve(name.lower())


def sandbox_install_hint(sandbox_type: str) -> str:
    key = sandbox_type.lower()
    if key == "local":
        key = "subprocess"
    return _EXTRA_HINTS.get(key, _INSTALL_HINT)


def optional_sandbox_attr(module_name: str, attr: str, default: T | None = None) -> Any | T | None:
    if not sandbox_package_available():
        return default
    try:
        return getattr(import_sandbox_module(module_name), attr)
    except (ImportError, AttributeError):
        return default
