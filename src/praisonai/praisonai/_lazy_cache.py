"""Single source of truth for thread-safe lazy loading of optional deps."""
import threading
import time
from typing import Callable, Dict, Optional, Tuple, Type, TypeVar

T = TypeVar("T")

#: Failures we treat as *transient* — an environment blip that may resolve on
#: its own (a keyring read racing a plugin install, a half-installed optional
#: dep, a one-shot config error on first import). These get a cool-down window
#: before the loader is retried, instead of being memoised for the process
#: lifetime. Structural failures (``ImportError``/``ValueError``/…) still fail
#: fast and stay cached.
_TRANSIENT_EXCEPTIONS: Tuple[Type[BaseException], ...] = (
    OSError,
    ConnectionError,
    TimeoutError,
)


class LazyCache:
    """Thread-safe double-checked lazy cache. Caches and re-raises terminal loader failures.

    Structural loader failures are cached permanently so a broken optional dep
    fails fast. Transient failures (see :data:`_TRANSIENT_EXCEPTIONS`) are cached
    only for ``retry_cooldown`` seconds so a long-lived process (``praisonai
    serve``) recovers automatically once the underlying condition clears, mirror-
    ing the cool-down ``PraisonAIDB._init_stores`` already uses. See #4945.

    Prefer constructing a scoped instance for multi-tenant callers instead of
    sharing the module-level singleton.
    """

    def __init__(self, retry_cooldown: float = 30.0) -> None:
        self._cache: Dict[str, object] = {}
        self._error_ts: Dict[str, float] = {}
        self._retry_cooldown = retry_cooldown
        self._lock = threading.Lock()

    def _raise_if_valid_cached_error(self, key: str, cached: BaseException) -> bool:
        """Re-raise a cached error unless its transient cool-down has expired.

        Returns ``True`` when the cool-down expired and the loader should be
        retried; otherwise raises the cached error.
        """
        if isinstance(cached, _TRANSIENT_EXCEPTIONS):
            if time.monotonic() - self._error_ts.get(key, 0.0) < self._retry_cooldown:
                raise cached
            return True  # cool-down expired: retry
        raise cached

    def get(self, key: str, loader: Callable[[], T]) -> Optional[T]:
        cached = self._cache.get(key, _MISSING)
        if cached is not _MISSING:
            if isinstance(cached, BaseException):
                self._raise_if_valid_cached_error(key, cached)  # may raise
            else:
                return cached  # type: ignore[return-value]
        with self._lock:
            cached = self._cache.get(key, _MISSING)
            if cached is not _MISSING:
                if isinstance(cached, BaseException):
                    self._raise_if_valid_cached_error(key, cached)  # may raise
                else:
                    return cached  # type: ignore[return-value]
            try:
                value: object = loader()
            except (KeyboardInterrupt, SystemExit):
                # Control-flow exceptions must propagate cleanly, never memoised.
                raise
            except BaseException as e:
                # Cache terminal loader failures so a broken optional dep fails
                # fast. Transient failures are timestamped so they expire.
                self._cache[key] = e
                self._error_ts[key] = time.monotonic()
                raise
            self._cache[key] = value
            self._error_ts.pop(key, None)
            return value  # type: ignore[return-value]

    def reset(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                self._cache.clear()
                self._error_ts.clear()
            else:
                self._cache.pop(key, None)
                self._error_ts.pop(key, None)


_MISSING = object()

_GLOBAL = LazyCache()
lazy_get = _GLOBAL.get
lazy_reset = _GLOBAL.reset