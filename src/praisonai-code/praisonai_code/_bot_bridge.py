"""Lazy access to ``praisonai-bot`` from ``praisonai-code``."""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any, TypeVar

T = TypeVar("T")

_INSTALL_HINT = "Install the bot package: pip install praisonai-bot"


def bot_package_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("praisonai_bot") is not None


def import_bot_module(name: str) -> ModuleType:
    if not name.startswith("praisonai_bot"):
        raise ValueError(f"Expected praisonai_bot module name, got {name!r}")
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise ImportError(f"{name} requires praisonai-bot. {_INSTALL_HINT}") from exc


def optional_bot_attr(module_name: str, attr: str, default: T | None = None) -> Any | T | None:
    if not bot_package_available():
        return default
    try:
        return getattr(import_bot_module(module_name), attr)
    except (ImportError, AttributeError):
        return default
