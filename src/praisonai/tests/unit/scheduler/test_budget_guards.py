"""Regression tests for #5765: max_cost guards and strong A2U task refs."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from praisonai.scheduler.agent_scheduler import AgentScheduler
from praisonai.scheduler.async_agent_scheduler import AsyncAgentScheduler


def test_sync_execute_with_retry_skips_when_budget_exhausted():
    """run_immediately calls _execute_with_retry directly; it must not bill past max_cost."""
    agent = Mock()
    scheduler = AgentScheduler(agent, "task", max_cost=0.0)

    scheduler._execute_with_retry(max_retries=1)

    agent.start.assert_not_called()
    assert scheduler._execution_count == 0
    assert scheduler._stop_event.is_set()


def test_sync_execute_once_skips_when_budget_exhausted():
    agent = Mock()
    scheduler = AgentScheduler(agent, "task", max_cost=1.0)
    scheduler._total_cost = 1.0

    assert scheduler.execute_once() is None
    agent.start.assert_not_called()


@pytest.mark.asyncio
async def test_async_execute_once_skips_when_budget_exhausted():
    agent = Mock()
    agent.astart = AsyncMock(return_value="result")
    scheduler = AsyncAgentScheduler(agent, "task", max_cost=1.0)
    scheduler._total_cost = 1.0

    assert await scheduler.execute_once() is None
    agent.astart.assert_not_called()


@pytest.mark.asyncio
async def test_a2u_publish_sync_holds_strong_task_ref():
    from praisonai.endpoints import a2u_server
    from praisonai.endpoints.a2u_server import A2UEvent, A2UEventBus

    assert isinstance(a2u_server._BACKGROUND_TASKS, set)

    bus = A2UEventBus()
    bus.publish_sync(A2UEvent(event_type="t", data={}))
    task = bus.last_publish_task()
    assert task in a2u_server._BACKGROUND_TASKS

    await task
    await asyncio.sleep(0)
    assert task not in a2u_server._BACKGROUND_TASKS
