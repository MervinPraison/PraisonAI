"""Single source of truth for thread-safe lazy loading of optional deps."""
import threading
from typing import Callable, Dict, Optional, TypeVar

T = TypeVar("T")


class LazyCache:
    """Thread-safe double-checked lazy cache. Caches None for ImportError."""

    def __init__(self) -> None:
        self._cache: Dict[str, object] = {}
        self._lock = threading.Lock()

    def get(self, key: str, loader: Callable[[], T]) -> Optional[T]:
        if key in self._cache:
            cached = self._cache[key]
            # Re-raise cached exception
            if isinstance(cached, ImportError):
                raise cached
            return cached  # type: ignore[return-value]
        with self._lock:
            if key in self._cache:
                cached = self._cache[key]
                if isinstance(cached, ImportError):
                    raise cached
                return cached  # type: ignore[return-value]
            try:
                value: object = loader()
            except ImportError as e:
                # Cache the exception and re-raise
                self._cache[key] = e
                raise
            self._cache[key] = value
            return value  # type: ignore[return-value]

    def reset(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                self._cache.clear()
            else:
                self._cache.pop(key, None)


_GLOBAL = LazyCache()
lazy_get = _GLOBAL.get
lazy_reset = _GLOBAL.reset