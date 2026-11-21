"""Interval schedules must not repeat an immediate run on the first tick."""

import asyncio
import threading
from unittest.mock import Mock

import pytest

from praisonai.scheduler.agent_scheduler import AgentScheduler
from praisonai.scheduler.async_agent_scheduler import AsyncAgentScheduler


@pytest.mark.parametrize("immediate", [True, False])
def test_sync_interval_start(immediate):
    scheduler = AgentScheduler(Mock(), "task")
    calls = []
    first = threading.Event()
    second = threading.Event()

    def execute(_):
        calls.append(None)
        first.set()
        if len(calls) == 2:
            second.set()

    scheduler._execute_with_retry = execute
    try:
        assert scheduler.start("1", run_immediately=immediate)
        assert first.wait(2)
        assert not second.wait(0.15)
        assert len(calls) == 1
        assert second.wait(2)
    finally:
        scheduler.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("immediate", [True, False])
async def test_async_interval_start(immediate):
    scheduler = AsyncAgentScheduler(Mock(), "task")
    calls = []
    first = asyncio.Event()
    second = asyncio.Event()

    async def execute(_):
        calls.append(None)
        first.set()
        if len(calls) == 2:
            second.set()

    scheduler._execute_with_retry = execute
    try:
        assert await scheduler.start("1", run_immediately=immediate)
        await asyncio.wait_for(first.wait(), timeout=2)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(second.wait(), timeout=0.15)
        assert len(calls) == 1
        await asyncio.wait_for(second.wait(), timeout=2)
    finally:
        await scheduler.stop()
