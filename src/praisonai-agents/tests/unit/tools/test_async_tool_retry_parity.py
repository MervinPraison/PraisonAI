"""execute_tool_async must retry a raised tool exception, like execute_tool does.

The async implementation flattens the exception into an error dict before any
policy can classify it; the retry verdict has to survive that flattening.
"""
import asyncio

import pytest

from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import ToolConfig
from praisonaiagents.tools.retry import RetryPolicy

FAST = ToolConfig(retry_policy=RetryPolicy(max_attempts=3, initial_delay_ms=0))


def _make_agent(exc, tool_config=FAST):
    calls = []

    def flaky():
        """Always fails."""
        calls.append(1)
        raise exc

    return Agent(instructions="x", tools=[flaky], tool_config=tool_config), calls


def _sync_runs(exc, **kw):
    agent, calls = _make_agent(exc, **kw)
    try:
        agent.execute_tool("flaky", {})
    except Exception:
        pass
    return len(calls)


def _async_runs(exc, **kw):
    agent, calls = _make_agent(exc, **kw)
    try:
        asyncio.run(agent.execute_tool_async("flaky", {}))
    except Exception:
        pass
    return len(calls)


def test_async_retries_a_raised_tool_exception():
    assert _async_runs(RuntimeError("boom")) == 3


def test_async_matches_sync_attempt_count():
    assert _async_runs(RuntimeError("boom")) == _sync_runs(RuntimeError("boom"))


@pytest.mark.parametrize("exc", [ValueError("bad"), TypeError("bad"), AttributeError("bad")])
def test_async_does_not_retry_programming_errors(exc):
    """Same terminal set the sync path uses — retrying these cannot help."""
    assert _async_runs(exc) == 1


def test_async_honours_max_attempts():
    policy = ToolConfig(retry_policy=RetryPolicy(max_attempts=2, initial_delay_ms=0))
    assert _async_runs(RuntimeError("boom"), tool_config=policy) == 2


def test_async_flattened_error_carries_the_retry_verdict():
    agent, _ = _make_agent(RuntimeError("boom"))
    result = asyncio.run(
        agent._execute_tool_async_impl("flaky", {}, None, None)
    )
    assert result["retryable"] is True

    agent2, _ = _make_agent(ValueError("bad"))
    result2 = asyncio.run(
        agent2._execute_tool_async_impl("flaky", {}, None, None)
    )
    assert result2["retryable"] is False
