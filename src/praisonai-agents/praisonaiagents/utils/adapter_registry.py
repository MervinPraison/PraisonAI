"""
Generic Adapter Registry

Provides a thread-safe, generic registry for protocol-based adapters.
Used by memory/adapters/registry.py and knowledge/adapters/registry.py to
avoid code duplication.
"""

import logging
import threading
from typing import Callable, Dict, Generic, List, Optional, Tuple, Type, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


class AdapterRegistry(Generic[T]):
    """
    Thread-safe generic registry for protocol-based adapters.

    Supports two registration modes:
    - **class**: instantiated on demand via ``register_adapter``
    - **factory**: called on demand via ``register_factory``

    Factory entries take priority over class entries when both exist for the
    same name, because factories can apply extra configuration logic.
    """

    def __init__(self, adapter_type_name: str = "adapter") -> None:
        self._adapters: Dict[str, Type[T]] = {}
        self._factories: Dict[str, Callable[..., T]] = {}
        self._lock = threading.Lock()
        self._type_name = adapter_type_name

    def register_adapter(self, name: str, adapter_class: Type[T]) -> None:
        """Register an adapter class instantiated on demand."""
        with self._lock:
            self._adapters[name] = adapter_class

    def register_factory(self, name: str, factory_func: Callable[..., T]) -> None:
        """Register a factory function that creates adapter instances."""
        with self._lock:
            self._factories[name] = factory_func

    def get_adapter(self, name: str, **kwargs) -> Optional[T]:
        """
        Return an adapter instance for *name*, or ``None`` if unavailable.

        Tries the factory first (if registered), then falls back to direct
        class instantiation.  Instantiation errors are logged at DEBUG level
        so callers can chain fallbacks without hiding genuine failures.
        """
        with self._lock:
            if name in self._factories:
                try:
                    return self._factories[name](**kwargs)
                except Exception as e:
                    logger.debug(
                        "%s factory '%s' failed: %s", self._type_name, name, e
                    )

            if name in self._adapters:
                try:
                    return self._adapters[name](**kwargs)
                except Exception as e:
                    logger.debug(
                        "%s adapter '%s' instantiation failed: %s",
                        self._type_name,
                        name,
                        e,
                    )

        return None

    def list_adapters(self) -> List[str]:
        """Return a sorted list of all registered adapter names."""
        with self._lock:
            return sorted(set(self._adapters.keys()) | set(self._factories.keys()))

    def is_available(self, name: str) -> bool:
        """Return ``True`` if *name* has a registered adapter or factory."""
        with self._lock:
            return name in self._adapters or name in self._factories

    def get_first_available(
        self, preferences: List[str], **kwargs
    ) -> Optional[Tuple[str, T]]:
        """
        Return the first successfully instantiated adapter from *preferences*.

        Args:
            preferences: Adapter names tried in order.
            **kwargs: Passed to the adapter constructor / factory.

        Returns:
            ``(name, instance)`` tuple, or ``None`` if none could be created.
        """
        for name in preferences:
            instance = self.get_adapter(name, **kwargs)
            if instance is not None:
                return name, instance
        return None
