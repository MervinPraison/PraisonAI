"""Tests for Per-Agent Concurrency Limiter (Gap 2).

Validates:
- ConcurrencyRegistry singleton
- Per-agent semaphore limits
- Default limit applies to unregistered agents
- Async acquire/release
- Thread safety
"""
import asyncio
import pytest


class TestConcurrencyRegistry:
    """Test ConcurrencyRegistry."""

    def test_singleton(self):
        from praisonaiagents.agent.concurrency import get_concurrency_registry
        r1 = get_concurrency_registry()
        r2 = get_concurrency_registry()
        assert r1 is r2

    def test_set_limit(self):
        from praisonaiagents.agent.concurrency import ConcurrencyRegistry
        reg = ConcurrencyRegistry()
        reg.set_limit("researcher", 2)
        assert reg.get_limit("researcher") == 2

    def test_default_limit(self):
        from praisonaiagents.agent.concurrency import ConcurrencyRegistry
        reg = ConcurrencyRegistry()
        # Unregistered agent gets default (no limit = 0 means unlimited)
        assert reg.get_limit("unknown_agent") == 0

    def test_set_default_limit(self):
        from praisonaiagents.agent.concurrency import ConcurrencyRegistry
        reg = ConcurrencyRegistry(default_limit=5)
        assert reg.get_limit("any_agent") == 5

    def test_remove_limit(self):
        from praisonaiagents.agent.concurrency import ConcurrencyRegistry
        reg = ConcurrencyRegistry()
        reg.set_limit("agent1", 3)
        reg.remove_limit("agent1")
        assert reg.get_limit("agent1") == 0  # back to default


class TestConcurrencyLimiting:
    """Test actual concurrency limiting via async acquire/release."""

    @pytest.mark.asyncio
    async def test_acquire_release(self):
        from praisonaiagents.agent.concurrency import ConcurrencyRegistry
        reg = ConcurrencyRegistry()
        reg.set_limit("agent_a", 1)
        # Should acquire immediately
        await reg.acquire("agent_a")
        # Release
        reg.release("agent_a")

    @pytest.mark.asyncio
    async def test_concurrency_limit_enforced(self):
        """Only N tasks can run concurrently per agent."""
        from praisonaiagents.agent.concurrency import ConcurrencyRegistry
        reg = ConcurrencyRegistry()
        reg.set_limit("agent_b", 2)

        active = []
        max_active = [0]

        async def task(name):
            await reg.acquire(name)
            active.append(1)
            max_active[0] = max(max_active[0], len(active))
            await asyncio.sleep(0.05)
            active.pop()
            reg.release(name)

        # Run 5 tasks, only 2 should be active at a time
        await asyncio.gather(*(task("agent_b") for _ in range(5)))
        assert max_active[0] <= 2

    @pytest.mark.asyncio
    async def test_unlimited_when_no_limit(self):
        """When limit=0 (unlimited), acquire is a no-op."""
        from praisonaiagents.agent.concurrency import ConcurrencyRegistry
        reg = ConcurrencyRegistry()
        # No limit set — should not block
        await reg.acquire("no_limit_agent")
        reg.release("no_limit_agent")

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager usage."""
        from praisonaiagents.agent.concurrency import ConcurrencyRegistry
        reg = ConcurrencyRegistry()
        reg.set_limit("ctx_agent", 1)
        async with reg.throttle("ctx_agent"):
            pass  # Should acquire and release cleanly

    def test_sync_acquire_release(self):
        """Test synchronous acquire/release for non-async code paths."""
        from praisonaiagents.agent.concurrency import ConcurrencyRegistry
        reg = ConcurrencyRegistry()
        reg.set_limit("sync_agent", 2)
        # Sync acquire should work
        reg.acquire_sync("sync_agent")
        reg.release("sync_agent")

    @pytest.mark.asyncio
    async def test_async_acquire_does_not_block_loop(self):
        """Async acquire waits on a loop-neutral semaphore without blocking the loop."""
        from praisonaiagents.agent.concurrency import ConcurrencyRegistry
        reg = ConcurrencyRegistry()
        reg.set_limit("loop_agent", 1)
        await reg.acquire("loop_agent")
        # Second acquire must block (limit reached) but must not deadlock the loop.
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(reg.acquire("loop_agent"), timeout=0.05)
        reg.release("loop_agent")
        await asyncio.wait_for(reg.acquire("loop_agent"), timeout=0.5)
        reg.release("loop_agent")

    def test_sync_and_async_share_one_pool(self):
        """Sync and async callers contend for the SAME per-agent permit pool."""
        from praisonaiagents.agent.concurrency import ConcurrencyRegistry
        reg = ConcurrencyRegistry()
        reg.set_limit("shared_agent", 1)
        reg.acquire_sync("shared_agent")

        async def try_acquire():
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(reg.acquire("shared_agent"), timeout=0.05)

        asyncio.run(try_acquire())
        reg.release("shared_agent")

    def test_limit_holds_across_threads(self):
        """A limit of 1 is a true global cap even across many threads/loops."""
        import threading
        from praisonaiagents.agent.concurrency import ConcurrencyRegistry
        reg = ConcurrencyRegistry()
        reg.set_limit("mt_agent", 1)

        active = [0]
        max_active = [0]
        state_lock = threading.Lock()

        def worker():
            async def run():
                await reg.acquire("mt_agent")
                with state_lock:
                    active[0] += 1
                    max_active[0] = max(max_active[0], active[0])
                await asyncio.sleep(0.02)
                with state_lock:
                    active[0] -= 1
                reg.release("mt_agent")
            asyncio.run(run())

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert max_active[0] == 1
