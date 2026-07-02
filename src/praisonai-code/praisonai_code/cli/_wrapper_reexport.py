"""Re-export a wrapper submodule into a praisonai-code bridge module."""

from __future__ import annotations

from types import ModuleType


def load_wrapper_module(wrapper_name: str) -> ModuleType:
    from praisonai_code._wrapper_bridge import import_wrapper_module

    return import_wrapper_module(wrapper_name)


def populate_from_module(target_globals: dict, source: ModuleType) -> None:
    for name, value in vars(source).items():
        if name.startswith("__"):
            continue
        target_globals[name] = value
