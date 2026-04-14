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
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._lock = threading.Lock()

    def set_limit(self, agent_name: str, max_concurrent: int) -> None:
        """Set concurrency limit for an agent.
        
        Args:
            agent_name: Agent identifier
            max_concurrent: Max concurrent tasks (0 = unlimited)
        """
        with self._lock:
            self._limits[agent_name] = max_concurrent
            # Reset semaphore so next acquire creates a fresh one
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

    def _get_semaphore(self, agent_name: str) -> Optional[asyncio.Semaphore]:
        """Get or create semaphore for agent. Returns None if unlimited."""
        with self._lock:
            limit = self._limits.get(agent_name, self._default_limit)
            if limit <= 0:
                return None
            if agent_name not in self._semaphores:
                self._semaphores[agent_name] = asyncio.Semaphore(limit)
            return self._semaphores[agent_name]

    async def acquire(self, agent_name: str) -> None:
        """Acquire concurrency slot for agent. No-op if unlimited."""
        sem = self._get_semaphore(agent_name)
        if sem is not None:
            await sem.acquire()

    def acquire_sync(self, agent_name: str) -> None:
        """Synchronous acquire — for non-async code paths.
        
        Note: This creates/reuses an event loop internally.
        Prefer async acquire() when possible.
        """
        sem = self._get_semaphore(agent_name)
        if sem is None:
            return
        try:
            asyncio.get_running_loop()
            # If we're in an async context, we can't block
            # Just try_acquire or no-op with warning
            if not sem._value > 0:
                logger.warning(
                    f"Sync acquire for '{agent_name}' while async loop running and semaphore full. "
                    f"Consider using async acquire() instead."
                )
            # Decrement manually for sync context
            sem._value = max(0, sem._value - 1)
        except RuntimeError:
            # No running loop — safe to use asyncio.run
            asyncio.get_event_loop().run_until_complete(sem.acquire())

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
