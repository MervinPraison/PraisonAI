"""Per-Agent Concurrency Limiter for PraisonAI Agents.

Provides a registry-based approach to limit concurrent task execution
per agent name. No Agent constructor param bloat — uses a global registry.

Usage:
    from praisonaiagents.agent.concurrency import get_concurrency_registry
    
    registry = get_concurrency_registry()
    registry.set_limit("researcher", 2)  # max 2 concurrent tasks
    
    # In async code:
    async with registry.throttle("researcher"):
        await do_work()
    
    # Or manual (pass the acquired handle back to release so a concurrent
    # set_limit()/remove_limit() cannot redirect the release onto a fresh
    # semaphore and inflate the cap):
    sem = await registry.acquire("researcher")
    try:
        await do_work()
    finally:
        registry.release("researcher", sem)
"""

import asyncio
import threading
from contextlib import asynccontextmanager
from typing import Dict, Optional

from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


class _DynamicLimiter:
    """Resizable counting limiter: capacity can change with holders outstanding.

    Unlike swapping a fresh threading.Semaphore on every retune (which lets
    holders of the old primitive and the release() path operate on different
    objects), this keeps one long-lived object per agent name and mutates its
    capacity in place. Every acquirer and every release() therefore always
    operate on the same shared state, so a retune takes effect immediately and
    the configured cap can never be silently exceeded. Loop-neutral: uses a
    threading.Condition so it is a true global cap across event loops/threads.
    """

    def __init__(self, limit: int):
        self._limit = limit
        self._held = 0
        self._cond = threading.Condition()

    def set_limit(self, limit: int) -> None:
        with self._cond:
            self._limit = limit
            self._cond.notify_all()

    def acquire(self, blocking: bool = True) -> bool:
        with self._cond:
            while self._limit > 0 and self._held >= self._limit:
                if not blocking:
                    return False
                self._cond.wait(timeout=0.05)
            self._held += 1
            return True

    def release(self) -> None:
        with self._cond:
            self._held = max(0, self._held - 1)
            self._cond.notify_all()

    def has_holders(self) -> bool:
        with self._cond:
            return self._held > 0


class ConcurrencyRegistry:
    """Registry for per-agent concurrency limits.

    Thread-safe. Each agent name maps to a loop-neutral, resizable limiter, so
    the limit is a true global cap across every event loop and thread and a
    retune takes effect immediately for in-flight holders.
    Limit of 0 means unlimited (no throttling).
    """

    def __init__(self, default_limit: int = 0):
        self._default_limit = default_limit
        self._limits: Dict[str, int] = {}
        # One long-lived, loop-neutral _DynamicLimiter per agent. Its capacity is
        # mutated in place on retune (never swapped for a fresh object), so every
        # acquirer and every release() always share the same state and the
        # configured cap can never be silently exceeded. Loop-neutral means the
        # per-agent limit is a true global cap under multi-loop / multi-thread
        # deployments; async callers poll without blocking their loop.
        self._limiters: Dict[str, _DynamicLimiter] = {}
        self._lock = threading.Lock()

    def set_limit(self, agent_name: str, max_concurrent: int) -> None:
        """Set concurrency limit for an agent.
        
        Args:
            agent_name: Agent identifier
            max_concurrent: Max concurrent tasks (0 = unlimited)
        """
        with self._lock:
            self._limits[agent_name] = max_concurrent
            # Mutate the existing limiter in place so the retune takes effect
            # immediately for in-flight holders without ever swapping the object.
            limiter = self._limiters.get(agent_name)
            if limiter is not None:
                limiter.set_limit(max_concurrent)

    def get_limit(self, agent_name: str) -> int:
        """Get concurrency limit for an agent."""
        with self._lock:
            return self._limits.get(agent_name, self._default_limit)

    def remove_limit(self, agent_name: str) -> None:
        """Remove concurrency limit for an agent (reverts to default).

        The limiter object is kept alive while any permit is still held, so
        in-flight acquire()/release() pairs keep operating on the same shared
        state; dropping it mid-flight would strand those permits and let a
        later set_limit() start from a fresh, empty count and admit work beyond
        the configured cap. Once no permits are outstanding it is safe to drop.
        """
        with self._lock:
            self._limits.pop(agent_name, None)
            # Retune the surviving limiter to unlimited so it stops blocking
            # while remaining the single accounting object for its holders.
            limiter = self._limiters.get(agent_name)
            if limiter is None:
                return
            limiter.set_limit(0)
            if not limiter.has_holders():
                self._limiters.pop(agent_name, None)

    def _get_limiter(self, agent_name: str) -> Optional[_DynamicLimiter]:
        """Get or create the loop-neutral limiter for an agent.

        Returns None only when the agent has never been given a limit (pure
        unlimited fast path). Once a limiter exists it is always returned — even
        while unlimited (limit 0) — so acquire() and release() stay symmetric
        across a mid-flight retune to/from unlimited and the count can never be
        corrupted. The same _DynamicLimiter is shared across every event loop
        and thread, so a configured limit is a true global cap.
        """
        with self._lock:
            limit = self._limits.get(agent_name, self._default_limit)
            limiter = self._limiters.get(agent_name)
            if limiter is None:
                if limit <= 0:
                    return None
                limiter = _DynamicLimiter(limit)
                self._limiters[agent_name] = limiter
            return limiter

    async def acquire(self, agent_name: str) -> Optional[threading.Semaphore]:
        """Acquire concurrency slot for agent. No-op if unlimited.

        Waits on the loop-neutral semaphore in short, cancellable polls so the
        running event loop is never blocked while other tasks hold permits, and
        a cancelled/timed-out await never leaves a thread blocked on acquire().

        Returns the exact semaphore instance acquired so the caller can release
        that same instance (see release()). Returns None when unlimited.
        """
<<<<<<< HEAD
        sem = self._get_semaphore(agent_name)
        if sem is None:
            return None
        while True:
            if sem.acquire(blocking=False):
                return sem
=======
        limiter = self._get_limiter(agent_name)
        if limiter is None:
            return
        while True:
            if limiter.acquire(blocking=False):
                return
>>>>>>> origin/main
            # Yield to the loop; on cancellation this raises and no permit leaks.
            await asyncio.sleep(0.005)

    def acquire_sync(self, agent_name: str) -> Optional[threading.Semaphore]:
        """Synchronous acquire — for non-async code paths.

        Prefer async acquire() when possible. Blocks the calling thread until a
        permit is available. Safe to call whether or not a loop is running in the
        current thread, since the semaphore is loop-neutral. Returns the exact
        semaphore instance acquired (None when unlimited) for release().
        """
<<<<<<< HEAD
        sem = self._get_semaphore(agent_name)
        if sem is not None:
            sem.acquire()
        return sem

    def release(self, agent_name: str, sem: Optional[threading.Semaphore] = None) -> None:
        """Release a concurrency slot for agent. No-op if unlimited.

        When ``sem`` (the instance returned by a matching acquire()) is given it
        is released directly. This matters because set_limit()/remove_limit()
        pop-and-replace the per-name semaphore: releasing by name alone could
        hit a *different* semaphore than the one acquire() took, silently
        inflating its permit count and corrupting the configured cap. Passing
        the acquired instance keeps release matched to its own acquire.
        """
        if sem is None:
            with self._lock:
                sem = self._semaphores.get(agent_name)
        if sem is not None:
            try:
                sem.release()
            except ValueError:
                pass  # Already fully released
=======
        limiter = self._get_limiter(agent_name)
        if limiter is not None:
            limiter.acquire()

    def release(self, agent_name: str) -> None:
        """Release concurrency slot for agent. No-op if unlimited."""
        with self._lock:
            limiter = self._limiters.get(agent_name)
        if limiter is not None:
            limiter.release()
>>>>>>> origin/main

    @asynccontextmanager
    async def throttle(self, agent_name: str):
        """Async context manager for throttled execution.
        
        Usage:
            async with registry.throttle("agent_name"):
                await do_work()
        """
        sem = await self.acquire(agent_name)
        try:
            yield
        finally:
            # Only release when this block actually acquired a permit. When
            # acquire() returned None (unlimited at entry) there is nothing to
            # release; falling back to a by-name lookup here would release a
            # semaphore this block never acquired if a concurrent set_limit()
            # created one meanwhile, inflating the cap past its configured
            # limit. Release the exact instance acquired so the release stays
            # matched to its own acquire.
            if sem is not None:
                self.release(agent_name, sem)


# Singleton
_registry: Optional[ConcurrencyRegistry] = None
_registry_lock = threading.Lock()


def get_concurrency_registry() -> ConcurrencyRegistry:
    """Get the global concurrency registry singleton."""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = ConcurrencyRegistry()
    return _registry
