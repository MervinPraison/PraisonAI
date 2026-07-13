"""Lazy access to ``praisonai-train`` from ``praisonai-code``."""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any, TypeVar

T = TypeVar("T")

_INSTALL_HINT = "Install the training package: pip install praisonai-train"


def train_package_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("praisonai_train") is not None


def import_train_module(name: str) -> ModuleType:
    if not name.startswith("praisonai_train"):
        raise ValueError(f"Expected praisonai_train module name, got {name!r}")
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise ImportError(f"{name} requires praisonai-train. {_INSTALL_HINT}") from exc


def optional_train_attr(module_name: str, attr: str, default: T | None = None) -> Any | T | None:
    if not train_package_available():
        return default
    try:
        return getattr(import_train_module(module_name), attr)
    except (ImportError, AttributeError):
        return default
