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
    
    Thread-safe. Each agent name maps to an asyncio.Semaphore.
    Limit of 0 means unlimited (no throttling).
    """

    def __init__(self, default_limit: int = 0):
        self._default_limit = default_limit
        self._limits: Dict[str, int] = {}
        # Keyed by (agent_name, running loop) so a cached asyncio.Semaphore is
        # never shared across event loops (which would raise "bound to a
        # different event loop" under multi-loop / multi-thread deployments).
        self._semaphores: Dict[tuple, asyncio.Semaphore] = {}
        self._lock = threading.Lock()

    def set_limit(self, agent_name: str, max_concurrent: int) -> None:
        """Set concurrency limit for an agent.
        
        Args:
            agent_name: Agent identifier
            max_concurrent: Max concurrent tasks (0 = unlimited)
        """
        with self._lock:
            self._limits[agent_name] = max_concurrent
            # Reset semaphores (across all loops) so next acquire creates fresh ones
            self._drop_agent_semaphores(agent_name)

    def get_limit(self, agent_name: str) -> int:
        """Get concurrency limit for an agent."""
        with self._lock:
            return self._limits.get(agent_name, self._default_limit)

    def remove_limit(self, agent_name: str) -> None:
        """Remove concurrency limit for an agent (reverts to default)."""
        with self._lock:
            self._limits.pop(agent_name, None)
            self._drop_agent_semaphores(agent_name)

    def _drop_agent_semaphores(self, agent_name: str) -> None:
        """Drop all loop-keyed semaphores for an agent. Caller must hold the lock."""
        for key in [k for k in self._semaphores if k[0] == agent_name]:
            self._semaphores.pop(key, None)

    def _get_semaphore(self, agent_name: str) -> Optional[asyncio.Semaphore]:
        """Get or create semaphore for agent on the running loop.

        Returns None if unlimited. The semaphore is keyed per running event loop
        so it is never reused across loops (which would raise a RuntimeError).
        """
        loop = asyncio.get_running_loop()
        with self._lock:
            limit = self._limits.get(agent_name, self._default_limit)
            if limit <= 0:
                return None
            key = (agent_name, loop)
            sem = self._semaphores.get(key)
            if sem is None:
                sem = asyncio.Semaphore(limit)
                self._semaphores[key] = sem
            return sem

    async def acquire(self, agent_name: str) -> None:
        """Acquire concurrency slot for agent. No-op if unlimited."""
        sem = self._get_semaphore(agent_name)
        if sem is not None:
            await sem.acquire()

    def acquire_sync(self, agent_name: str) -> None:
        """Synchronous acquire — for non-async code paths.
        
        Prefer async acquire() when possible.
        If called while an event loop is already running in the current thread,
        this method raises RuntimeError to avoid deadlock.
        """
        with self._lock:
            limit = self._limits.get(agent_name, self._default_limit)
        if limit <= 0:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — safe to create one. The semaphore must be
            # created and acquired inside this loop so it binds to it.
            loop = asyncio.new_event_loop()
            try:
                async def _acquire():
                    sem = self._get_semaphore(agent_name)
                    if sem is not None:
                        await sem.acquire()
                loop.run_until_complete(_acquire())
            finally:
                loop.close()
        else:
            raise RuntimeError(
                f"acquire_sync('{agent_name}') cannot be called with a running event loop; "
                "use async acquire() in async contexts."
            )

    def release(self, agent_name: str) -> None:
        """Release concurrency slot for agent. No-op if unlimited."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        with self._lock:
            if loop is not None:
                sem = self._semaphores.get((agent_name, loop))
            else:
                # No running loop: fall back to the sole semaphore if unambiguous
                candidates = [v for k, v in self._semaphores.items() if k[0] == agent_name]
                sem = candidates[0] if len(candidates) == 1 else None
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
