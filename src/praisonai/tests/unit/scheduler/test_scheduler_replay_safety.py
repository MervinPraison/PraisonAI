"""Scheduler retries must not re-run a task that carries an effectful tool (Issue #6639)."""

import asyncio
from unittest.mock import Mock, patch

import pytest

from praisonai.scheduler.agent_scheduler import AgentScheduler
from praisonai.scheduler.async_agent_scheduler import AsyncAgentScheduler


def _tool(name, restart_safe=None):
    def fn():
        return name
    fn.__name__ = name
    if restart_safe is not None:
        fn.restart_safe = restart_safe
    return fn


def _agent(*tools):
    agent = Mock()
    agent.tools = list(tools)
    agent.agents = None
    agent.start = Mock(side_effect=RuntimeError("boom"))
    return agent


def _run_sync(agent, max_retries=3):
    scheduler = AgentScheduler(agent, "task")
    with patch.object(scheduler._stop_event, "wait", return_value=False):
        scheduler._execute_with_retry(max_retries)
    return scheduler


def test_effectful_tool_blocks_rerun():
    agent = _agent(_tool("send_email", restart_safe=False))
    on_failure = Mock()
    scheduler = AgentScheduler(agent, "task", on_failure=on_failure)
    with patch.object(scheduler._stop_event, "wait", return_value=False):
        scheduler._execute_with_retry(3)
    assert agent.start.call_count == 1
    assert scheduler._failure_count == 1
    on_failure.assert_called_once()


def test_idempotent_and_undeclared_tools_still_retry():
    agent = _agent(_tool("search", restart_safe=True), _tool("lookup"))
    _run_sync(agent)
    assert agent.start.call_count == 3


def test_effectful_tool_on_team_member_blocks_rerun():
    member = Mock()
    member.tools = [_tool("charge_card", restart_safe=False)]
    team = _agent()
    team.agents = [member]
    _run_sync(team)
    assert team.start.call_count == 1


def test_async_effectful_tool_blocks_rerun():
    agent = _agent(_tool("send_email", restart_safe=False))
    del agent.astart
    scheduler = AsyncAgentScheduler(agent, "task")

    async def run():
        with patch.object(scheduler, "_sleep_or_stop", side_effect=lambda _: asyncio.sleep(0, result=False)):
            await scheduler._execute_with_retry(3)

    asyncio.run(run())
    assert agent.start.call_count == 1
    assert scheduler._failure_count == 1


def test_async_undeclared_tools_still_retry():
    agent = _agent(_tool("lookup"))
    del agent.astart
    scheduler = AsyncAgentScheduler(agent, "task")

    async def fake_sleep(_):
        return False

    async def run():
        with patch.object(scheduler, "_sleep_or_stop", side_effect=fake_sleep):
            await scheduler._execute_with_retry(3)

    asyncio.run(run())
    assert agent.start.call_count == 3
