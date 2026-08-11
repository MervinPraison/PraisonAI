"""Generic registry — the single extension point for pluggable data components.

Add a recipe or a QC check by decorating a class with ``@recipes.register`` /
``@checks.register``; it becomes available to the YAML-driven CLI with no other
code change (DRY, open/closed).
"""
from __future__ import annotations

from typing import Callable, TypeVar

T = TypeVar("T")


class Registry:
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._items: dict[str, object] = {}

    def register(self, cls: Callable[[], T]) -> Callable[[], T]:
        inst = cls()
        name = getattr(inst, "name", None)
        if not name:
            raise ValueError(f"{cls.__name__} must define a 'name' attribute")
        if name in self._items:
            raise ValueError(f"duplicate {self.kind} '{name}'")
        self._items[name] = inst
        return cls

    def get(self, name: str) -> object:
        try:
            return self._items[name]
        except KeyError:
            raise KeyError(
                f"unknown {self.kind} '{name}'; available: {sorted(self._items)}"
            ) from None

    def all(self) -> list:
        return list(self._items.values())

    def names(self) -> list[str]:
        return sorted(self._items)


recipes = Registry("recipe")
checks = Registry("check")
