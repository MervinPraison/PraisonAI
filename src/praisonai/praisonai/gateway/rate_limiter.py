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

            # Overflow fail-closed hardening: if the key map is still saturated
            # after pruning and this is a *new* key, reject it closed rather than
            # admitting it (and evicting real state). Existing lockouts are
            # preserved above, so a fresh-IP flood can neither exhaust memory nor
            # evict a genuine lockout. Keys already present in ``_lockouts`` (even
            # ones whose lockout has just expired) are allowed through so a
            # returning client can clear its stale lockout entry below rather than
            # being permanently trapped until the next prune cycle.
            if (
                key not in self._buckets
                and key not in self._lockouts
                and (len(self._buckets) + len(self._lockouts)) >= self._max_keys
            ):
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


class PreauthConnectionBudget:
    """Per-source-IP budget of concurrent *unauthenticated* WebSocket connections.

    Bounds how many half-open (accepted but not yet authenticated) sockets a
    single source IP may hold at once. A slot is acquired at accept, before
    auth, and released on auth-success or connection close. This prevents an
    attacker who passes the origin check from parking many never-authenticating
    connections and exhausting accept/session/bookkeeping resources up to
    ``max_connections``.

    Fail-closed semantics:
        Unresolvable IPs (e.g. a trusted-proxy deployment whose forwarded
        headers are missing) are collapsed into one shared bounded bucket via
        ``unresolved_key`` so the cap stays enforced rather than failing open.

    Thread-safe via ``threading.Lock``.

    Args:
        max_per_ip: Maximum concurrent unauthenticated connections per IP
            (default 32). ``0`` disables the budget entirely.
        unresolved_key: Bucket key used for IPs that could not be resolved.

    Example::

        budget = PreauthConnectionBudget(max_per_ip=32)
        if not budget.acquire(client_ip):
            await websocket.close(code=4029)   # too many unauth connections
            return
        try:
            ...  # origin check, accept, auth
        finally:
            budget.release(client_ip)
    """

    def __init__(
        self,
        max_per_ip: int = 32,
        unresolved_key: str = "__unresolved__",
    ) -> None:
        self._max = max_per_ip
        self._unresolved_key = unresolved_key
        self._lock = threading.Lock()
        self._counts: Dict[str, int] = {}

    def _key(self, ip: str) -> str:
        if not ip or ip == "unknown":
            return self._unresolved_key
        return ip

    def acquire(self, ip: str) -> bool:
        """Reserve one unauthenticated slot for ``ip``.

        Returns ``True`` if a slot was acquired, ``False`` if the per-IP budget
        is exhausted (caller should reject the upgrade). When ``max_per_ip`` is
        ``0`` the budget is disabled and this always returns ``True`` without
        tracking state.
        """
        if self._max <= 0:
            return True
        key = self._key(ip)
        with self._lock:
            current = self._counts.get(key, 0)
            if current >= self._max:
                return False
            self._counts[key] = current + 1
            return True

    def release(self, ip: str) -> None:
        """Release a previously-acquired slot for ``ip`` (idempotent-safe)."""
        if self._max <= 0:
            return
        key = self._key(ip)
        with self._lock:
            current = self._counts.get(key, 0)
            if current <= 1:
                self._counts.pop(key, None)
            else:
                self._counts[key] = current - 1

    def active(self, ip: str) -> int:
        """Current number of unauthenticated slots held by ``ip``."""
        with self._lock:
            return self._counts.get(self._key(ip), 0)


class UnauthorizedFloodGuard:
    """Per-connection guard that closes a socket after repeated unauthorized frames.

    A hostile or misconfigured client that keeps sending frames it lacks the
    scope for can flood logs and burn per-frame work. This guard counts
    unauthorized frames on a single connection and signals the caller to close
    after ``max_unauthorized`` of them. It also log-samples: the first
    unauthorized frame is loggable, then every ``log_every`` th one, so the log
    stream cannot be flooded.

    One instance is created *per connection* (not shared), so no locking is
    needed — a WebSocket receive loop is single-tasked per connection.

    Args:
        max_unauthorized: Close the connection once this many unauthorized
            frames have been seen (default 10). ``0`` disables the guard.
        log_every: Emit a log line for the 1st unauthorized frame, then every
            ``log_every`` th one thereafter (default 5).

    Example::

        guard = UnauthorizedFloodGuard(max_unauthorized=10)
        # inside the receive loop, when a frame is unauthorized:
        should_close = guard.note_unauthorized()
        if guard.should_log():
            logger.warning("unauthorized frame (%d suppressed)", guard.suppressed)
        if should_close:
            await websocket.close(code=4028)   # unauthorized flood -> close
            return
    """

    def __init__(self, max_unauthorized: int = 10, log_every: int = 5) -> None:
        self._max = max_unauthorized
        self._log_every = max(1, log_every)
        self._count = 0
        self._logged = 0

    def note_unauthorized(self) -> bool:
        """Record one unauthorized frame.

        Returns ``True`` if the limit has been reached and the caller should
        close the connection. When ``max_unauthorized`` is ``0`` the guard is
        disabled and this always returns ``False``.
        """
        self._count += 1
        if self._max <= 0:
            return False
        return self._count >= self._max

    def should_log(self) -> bool:
        """Whether this unauthorized frame should be logged (log-sampling).

        Logs the first unauthorized frame, then every ``log_every`` th one.
        Call once per unauthorized frame *after* ``note_unauthorized``.
        """
        if self._count == 1 or (self._count % self._log_every) == 0:
            self._logged += 1
            return True
        return False

    @property
    def count(self) -> int:
        """Total unauthorized frames seen on this connection."""
        return self._count

    @property
    def suppressed(self) -> int:
        """Number of unauthorized frames not logged (suppressed) so far."""
        return max(0, self._count - self._logged)
