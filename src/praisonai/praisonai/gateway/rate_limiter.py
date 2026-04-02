"""
Thread-safe in-memory rate limiter for PraisonAI gateway endpoints.

Protects authentication and approval endpoints against brute-force attacks
by tracking request counts within sliding time windows.

This is a *heavy implementation* and lives in the wrapper, not the core SDK.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass
class _Bucket:
    """Token-bucket state for a single key."""

    count: int = 0
    window_start: float = field(default_factory=time.time)


class AuthRateLimiter:
    """Sliding-window rate limiter keyed by (endpoint, identity).

    Thread-safe via ``threading.Lock`` — usable from both sync and async
    contexts (async callers should wrap calls in ``asyncio.to_thread`` for
    long-running hot paths, but the lock is so short-lived that contention
    is negligible for gateway workloads).

    Memory bounds:
        Automatically prunes expired entries when the internal dict exceeds
        ``max_keys``.  This prevents unbounded memory growth from many
        distinct IPs / identities.

    Args:
        max_attempts: Maximum requests per window (default 5).
        window_seconds: Window duration in seconds (default 60).
        lockout_seconds: Cooldown after limit exceeded (default 300 = 5 min).
        max_keys: Maximum tracked keys before forced pruning (default 10_000).

    Example::

        limiter = AuthRateLimiter(max_attempts=3, window_seconds=60)

        if not limiter.allow("auth", client_ip):
            return JSONResponse({"error": "Too many attempts"}, status_code=429)
    """

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: float = 60.0,
        lockout_seconds: float = 300.0,
        max_keys: int = 10_000,
    ) -> None:
        self._max = max_attempts
        self._window = window_seconds
        self._lockout = lockout_seconds
        self._max_keys = max_keys
        self._lock = threading.Lock()
        # (endpoint, identity) -> _Bucket
        self._buckets: Dict[Tuple[str, str], _Bucket] = {}
        # (endpoint, identity) -> lockout_expires_at
        self._lockouts: Dict[Tuple[str, str], float] = {}

    # ── Public API ────────────────────────────────────────────────────

    def allow(self, endpoint: str, identity: str) -> bool:
        """Check whether the request is allowed and count it.

        Returns ``True`` if the request may proceed, ``False`` if rate-limited.
        """
        key = (endpoint, identity)
        now = time.time()

        with self._lock:
            # Auto-prune if memory grows too large
            if len(self._buckets) + len(self._lockouts) > self._max_keys:
                self._prune_locked(now)

            # Check lockout first
            lockout_until = self._lockouts.get(key)
            if lockout_until and now < lockout_until:
                return False

            # Clear expired lockout
            if lockout_until and now >= lockout_until:
                self._lockouts.pop(key, None)

            bucket = self._buckets.get(key)

            # New window or expired window
            if bucket is None or (now - bucket.window_start) >= self._window:
                self._buckets[key] = _Bucket(count=1, window_start=now)
                return True

            # Within window
            bucket.count += 1
            if bucket.count > self._max:
                # Trigger lockout
                self._lockouts[key] = now + self._lockout
                del self._buckets[key]
                return False

            return True

    def reset(self, endpoint: str, identity: str) -> None:
        """Reset rate limit state for a key (e.g. after successful auth)."""
        key = (endpoint, identity)
        with self._lock:
            self._buckets.pop(key, None)
            self._lockouts.pop(key, None)

    def time_until_allowed(self, endpoint: str, identity: str) -> float:
        """Seconds until the key is unblocked (0.0 if already allowed)."""
        key = (endpoint, identity)
        now = time.time()
        with self._lock:
            lockout_until = self._lockouts.get(key)
            if lockout_until and now < lockout_until:
                return lockout_until - now
            return 0.0

    def prune(self) -> int:
        """Remove expired buckets and lockouts.  Returns count removed."""
        now = time.time()
        with self._lock:
            return self._prune_locked(now)

    # ── Internal ──────────────────────────────────────────────────────

    def _prune_locked(self, now: float) -> int:
        """Remove expired entries (caller holds lock). Returns count removed."""
        removed = 0

        expired_buckets = [
            k for k, b in self._buckets.items()
            if (now - b.window_start) >= self._window
        ]
        for k in expired_buckets:
            del self._buckets[k]
            removed += 1

        expired_lockouts = [
            k for k, t in self._lockouts.items() if now >= t
        ]
        for k in expired_lockouts:
            del self._lockouts[k]
            removed += 1

        return removed
