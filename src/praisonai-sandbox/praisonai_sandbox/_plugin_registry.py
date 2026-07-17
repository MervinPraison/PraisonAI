"""Plugin registry base for praisonai-sandbox.

Prefers the shared implementation from ``praisonai-code`` when installed so the
two packages stay in lock-step, but falls back to a self-contained
implementation so ``praisonai-sandbox`` works standalone (``pip install
praisonai-sandbox`` without ``praisonai-code``). Both expose the same public
surface used by :class:`SandboxRegistry`: ``__init__(entry_point_group=,
builtins=)``, ``resolve``, ``create``, ``list_names``, ``register`` and the
``default()`` classmethod.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__all__ = ["PluginRegistry", "create_lazy_getattr", "logger"]

try:  # Prefer the shared praisonai-code registry when available.
    from praisonai_sandbox._code_bridge import code_available

    if not code_available():
        raise ImportError("praisonai-code not installed")

    from praisonai_sandbox._code_bridge import import_code_module

    _registry_mod = import_code_module("praisonai_code._registry")
    PluginRegistry = _registry_mod.PluginRegistry
    create_lazy_getattr = _registry_mod.create_lazy_getattr
except ImportError:
    import threading
    from importlib.metadata import entry_points
    from typing import Callable, Dict, Generic, Optional, Type, TypeVar

    T = TypeVar("T")

    class PluginRegistry(Generic[T]):
        """Self-contained fallback registry (builtins + entry points)."""

        _default_locks_guard = threading.Lock()

        def __init__(
            self,
            *,
            entry_point_group: str,
            builtins: Optional[Dict[str, Callable[[], Type[T]]]] = None,
            discover_entry_points: bool = True,
        ) -> None:
            self._entry_point_group = entry_point_group
            self._loaders: Dict[str, Callable[[], Type[T]]] = {}
            self._items: Dict[str, Type[T]] = {}
            self._lock = threading.RLock()

            if builtins:
                for name, loader in builtins.items():
                    self._loaders[name.lower()] = loader

            if discover_entry_points:
                try:
                    for ep in entry_points(group=self._entry_point_group):
                        self._loaders[ep.name.lower()] = ep.load
                except Exception:
                    logger.debug(
                        "Entry points not available for group %s",
                        self._entry_point_group,
                    )

        def register(self, name: str, cls: Type[T]) -> None:
            with self._lock:
                key = name.lower()
                self._loaders[key] = lambda: cls
                self._items[key] = cls

        def resolve(self, name: str) -> Type[T]:
            key = name.lower()
            with self._lock:
                cls = self._items.get(key)
                if cls is not None:
                    return cls
                loader = self._loaders.get(key)
                if loader is None:
                    available = sorted(self._loaders.keys())
                    raise ValueError(
                        f"Unknown {self._entry_point_group} plugin: {name!r}. "
                        f"Available: {available}"
                    )
            try:
                cls = loader()
            except ImportError as exc:
                raise ValueError(
                    f"Plugin {name!r} is registered but its dependencies "
                    f"are not installed: {exc}"
                ) from exc
            except Exception as exc:  # noqa: BLE001 -- external plugin boundary
                raise ValueError(
                    f"Plugin {name!r} failed to load: {exc}"
                ) from exc
            with self._lock:
                if self._loaders.get(key) is loader:
                    self._items[key] = cls
                return cls

        def create(self, name: str, *args, **kwargs) -> T:
            return self.resolve(name)(*args, **kwargs)

        def list_names(self) -> list[str]:
            with self._lock:
                return sorted(self._loaders.keys())

        def is_available(self, name: str) -> bool:
            try:
                self.resolve(name)
                return True
            except ValueError:
                return False

        @classmethod
        def default(cls) -> "PluginRegistry[T]":
            cache_key = "_default_instance"
            lock_key = "_default_instance_lock"
            if lock_key not in cls.__dict__:
                with PluginRegistry._default_locks_guard:
                    if lock_key not in cls.__dict__:
                        setattr(cls, lock_key, threading.Lock())
            cache = cls.__dict__.get(cache_key)
            if cache is not None:
                return cache
            with getattr(cls, lock_key):
                cache = cls.__dict__.get(cache_key)
                if cache is None:
                    cache = cls()
                    setattr(cls, cache_key, cache)
                return cache

    def create_lazy_getattr(registry: "PluginRegistry[T]") -> Callable[[str], T]:
        import inspect

        frame = inspect.currentframe()
        if frame and frame.f_back:
            module_name = frame.f_back.f_globals.get("__name__", "unknown")
        else:
            module_name = "unknown"

        def __getattr__(name: str) -> T:
            try:
                return registry.resolve(name)
            except ValueError:
                raise AttributeError(
                    f"module {module_name!r} has no attribute {name!r}"
                ) from None

        return __getattr__
