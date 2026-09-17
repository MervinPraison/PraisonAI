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
    
    # Or manual:
    await registry.acquire("researcher")
    try:
        await do_work()
    finally:
        registry.release("researcher")
"""

import asyncio
import threading
from contextlib import asynccontextmanager
from typing import Dict, Optional

from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


class ConcurrencyRegistry:
    """Registry for per-agent concurrency limits.

    Thread-safe. Each agent name maps to a loop-neutral threading.Semaphore, so
    the limit is a true global cap across every event loop and thread.
    Limit of 0 means unlimited (no throttling).
    """

    def __init__(self, default_limit: int = 0):
        self._default_limit = default_limit
        self._limits: Dict[str, int] = {}
        # One loop-neutral threading.Semaphore per agent. Unlike asyncio.Semaphore
        # (which binds to the loop it is first awaited on), a threading.Semaphore
        # is shared safely across every event loop and thread, so the per-agent
        # limit is a true global cap under multi-loop / multi-thread deployments.
        # Async callers acquire it in an executor so they never block their loop.
        self._semaphores: Dict[str, threading.Semaphore] = {}
        self._lock = threading.Lock()

    def set_limit(self, agent_name: str, max_concurrent: int) -> None:
        """Set concurrency limit for an agent.
        
        Args:
            agent_name: Agent identifier
            max_concurrent: Max concurrent tasks (0 = unlimited)
        """
        with self._lock:
            self._limits[agent_name] = max_concurrent
            # Reset semaphore so next acquire creates a fresh one at the new limit
            self._semaphores.pop(agent_name, None)

    def get_limit(self, agent_name: str) -> int:
        """Get concurrency limit for an agent."""
        with self._lock:
            return self._limits.get(agent_name, self._default_limit)

    def remove_limit(self, agent_name: str) -> None:
        """Remove concurrency limit for an agent (reverts to default)."""
        with self._lock:
            self._limits.pop(agent_name, None)
            self._semaphores.pop(agent_name, None)

    def _get_semaphore(self, agent_name: str) -> Optional[threading.Semaphore]:
        """Get or create the loop-neutral semaphore for an agent.

        Returns None if unlimited. The same threading.Semaphore is shared across
        every event loop and thread, so the configured limit is a true global cap.
        """
        with self._lock:
            limit = self._limits.get(agent_name, self._default_limit)
            if limit <= 0:
                return None
            sem = self._semaphores.get(agent_name)
            if sem is None:
                sem = threading.Semaphore(limit)
                self._semaphores[agent_name] = sem
            return sem

    async def acquire(self, agent_name: str) -> None:
        """Acquire concurrency slot for agent. No-op if unlimited.

        Waits on the loop-neutral semaphore in short, cancellable polls so the
        running event loop is never blocked while other tasks hold permits, and
        a cancelled/timed-out await never leaves a thread blocked on acquire().
        """
        sem = self._get_semaphore(agent_name)
        if sem is None:
            return
        while True:
            if sem.acquire(blocking=False):
                return
            # Yield to the loop; on cancellation this raises and no permit leaks.
            await asyncio.sleep(0.005)

    def acquire_sync(self, agent_name: str) -> None:
        """Synchronous acquire — for non-async code paths.

        Prefer async acquire() when possible. Blocks the calling thread until a
        permit is available. Safe to call whether or not a loop is running in the
        current thread, since the semaphore is loop-neutral.
        """
        sem = self._get_semaphore(agent_name)
        if sem is not None:
            sem.acquire()

    def release(self, agent_name: str) -> None:
        """Release concurrency slot for agent. No-op if unlimited."""
        with self._lock:
            sem = self._semaphores.get(agent_name)
        if sem is not None:
            try:
                sem.release()
            except ValueError:
                pass  # Already fully released

    @asynccontextmanager
    async def throttle(self, agent_name: str):
        """Async context manager for throttled execution.
        
        Usage:
            async with registry.throttle("agent_name"):
                await do_work()
        """
        await self.acquire(agent_name)
        try:
            yield
        finally:
            self.release(agent_name)


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
