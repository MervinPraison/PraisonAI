"""Lazy access to ``praisonai-deploy`` from ``praisonai-code``."""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any, TypeVar

T = TypeVar("T")

_INSTALL_HINT = "Install the deployment package: pip install praisonai-deploy"


def deploy_package_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("praisonai_deploy") is not None


def import_deploy_module(name: str) -> ModuleType:
    if not name.startswith("praisonai_deploy"):
        raise ValueError(f"Expected praisonai_deploy module name, got {name!r}")
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise ImportError(f"{name} requires praisonai-deploy. {_INSTALL_HINT}") from exc


def optional_deploy_attr(module_name: str, attr: str, default: T | None = None) -> Any | T | None:
    if not deploy_package_available():
        return default
    try:
        return getattr(import_deploy_module(module_name), attr)
    except (ImportError, AttributeError):
        return default
