"""Tests for recovery-triggered outbox re-drain (Issue #4043).

When a channel recovers from a transient outage, the supervisor must re-attempt
anything the durable outbox held through the outage — instead of leaving it
undelivered until the next inbound ``chat()`` turn or a process restart.
"""

from __future__ import annotations

import asyncio

import pytest

from praisonai_bot.bots._resilience import BackoffPolicy
from praisonai_bot.gateway.supervisor import ChannelState, ChannelSupervisor


def _fast_supervisor() -> ChannelSupervisor:
    # Near-zero backoff so the recoverable-retry path is exercised quickly.
    return ChannelSupervisor(policy=BackoffPolicy(initial_ms=1, max_ms=1, jitter=0.0))


def test_recovery_triggers_outbox_drain():
    """A transient outage then reconnect -> adapter.drain_outbox() is fired."""

    drained = asyncio.Event()

    class _Adapter:
        def __init__(self):
            self.drain_calls = 0

        async def drain_outbox(self):
            self.drain_calls += 1
            drained.set()
            return (1, 0)

    class _Bot:
        platform = "slack"

        def __init__(self):
            self.adapter = _Adapter()

    bot = _Bot()
    calls = {"n": 0}
    running = asyncio.Event()

    async def start_fn(name, b):
        calls["n"] += 1
        if calls["n"] == 1:
            # First boot: transient (recoverable) outage.
            raise ConnectionError("connection reset by peer")
        # Reconnected: hold the channel open.
        running.set()
        await asyncio.Event().wait()

    sup = _fast_supervisor()

    async def scenario():
        task = asyncio.create_task(sup.run("slack", bot, start_fn))
        # Recovery drain must fire once the channel comes back after the outage.
        await asyncio.wait_for(drained.wait(), timeout=2.0)
        await asyncio.wait_for(running.wait(), timeout=2.0)
        assert bot.adapter.drain_calls == 1
        assert sup.get_status("slack").state == ChannelState.RUNNING

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(asyncio.wait_for(scenario(), timeout=5.0))


def test_clean_first_start_does_not_drain():
    """A channel that starts cleanly (no prior outage) must NOT re-drain."""

    class _Adapter:
        def __init__(self):
            self.drain_calls = 0

        async def drain_outbox(self):
            self.drain_calls += 1
            return (0, 0)

    class _Bot:
        platform = "slack"

        def __init__(self):
            self.adapter = _Adapter()

    bot = _Bot()
    running = asyncio.Event()

    async def start_fn(name, b):
        running.set()
        await asyncio.Event().wait()

    sup = _fast_supervisor()

    async def scenario():
        task = asyncio.create_task(sup.run("slack", bot, start_fn))
        await asyncio.wait_for(running.wait(), timeout=2.0)
        # Give any stray scheduled drain a chance to run before asserting.
        await asyncio.sleep(0.05)
        assert bot.adapter.drain_calls == 0

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(asyncio.wait_for(scenario(), timeout=5.0))


def test_recovery_drain_without_hook_is_noop():
    """A bot/adapter with no drain_outbox() must recover without error."""

    class _Bot:
        platform = "slack"
        adapter = object()  # no drain_outbox

    calls = {"n": 0}
    running = asyncio.Event()

    async def start_fn(name, b):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("connection reset by peer")
        running.set()
        await asyncio.Event().wait()

    sup = _fast_supervisor()

    async def scenario():
        task = asyncio.create_task(sup.run("slack", _Bot(), start_fn))
        await asyncio.wait_for(running.wait(), timeout=2.0)
        assert sup.get_status("slack").state == ChannelState.RUNNING

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(asyncio.wait_for(scenario(), timeout=5.0))


def test_recovery_drain_error_does_not_wedge_supervision():
    """A failing re-drain is swallowed; the channel still runs."""

    class _Adapter:
        async def drain_outbox(self):
            raise RuntimeError("outbox is temporarily unavailable")

    class _Bot:
        platform = "slack"
        adapter = _Adapter()

    calls = {"n": 0}
    running = asyncio.Event()

    async def start_fn(name, b):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("connection reset by peer")
        running.set()
        await asyncio.Event().wait()

    sup = _fast_supervisor()

    async def scenario():
        task = asyncio.create_task(sup.run("slack", _Bot(), start_fn))
        await asyncio.wait_for(running.wait(), timeout=2.0)
        await asyncio.sleep(0.05)
        assert sup.get_status("slack").state == ChannelState.RUNNING

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(asyncio.wait_for(scenario(), timeout=5.0))
