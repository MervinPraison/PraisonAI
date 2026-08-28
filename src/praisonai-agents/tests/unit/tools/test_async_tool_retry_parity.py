"""execute_tool_async must retry a raised tool exception, like execute_tool does.

The async implementation flattens the exception into an error dict before any
policy can classify it; the retry verdict has to survive that flattening.
"""
import asyncio

import pytest

from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import ToolConfig
from praisonaiagents.errors import ToolExecutionError
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
    assert result["_praison_retryable"] is True

    agent2, _ = _make_agent(ValueError("bad"))
    result2 = asyncio.run(
        agent2._execute_tool_async_impl("flaky", {}, None, None)
    )
    assert result2["_praison_retryable"] is False


def test_async_honours_terminal_tool_execution_error():
    """A ToolExecutionError(is_retryable=False) is terminal — its explicit
    verdict must be preserved, not overwritten to retryable, so the tool runs
    exactly once (parity with the sync path, which re-raises it verbatim)."""
    terminal = ToolExecutionError(
        "terminal failure", tool_name="flaky", is_retryable=False
    )
    assert _async_runs(terminal) == 1

    agent, _ = _make_agent(terminal)
    result = asyncio.run(
        agent._execute_tool_async_impl("flaky", {}, None, None)
    )
    assert result["_praison_retryable"] is False


def test_async_honours_retryable_tool_execution_error():
    """A ToolExecutionError(is_retryable=True) keeps its explicit retry verdict."""
    retryable = ToolExecutionError(
        "transient failure", tool_name="flaky", is_retryable=True
    )
    agent, _ = _make_agent(retryable)
    result = asyncio.run(
        agent._execute_tool_async_impl("flaky", {}, None, None)
    )
    assert result["_praison_retryable"] is True


def test_a_tools_own_retryable_field_does_not_drive_the_retry_loop():
    """'retryable' is a common key in API-wrapper results. It is the tool's payload,
    not our control plane, and must not cause re-execution.

    The tool *returns* an error dict, so execute_tool surfaces it as a terminal
    ToolExecutionError (existing contract); the body must run exactly once.
    """
    calls = []

    def upstream(x: str = "") -> dict:
        calls.append(1)
        return {"error": "upstream 503", "retryable": True}

    try:
        Agent(
            name="t", instructions="x", tools=[upstream], tool_config=FAST
        ).execute_tool("upstream", {})
    except Exception:
        pass
    assert len(calls) == 1


def test_framework_verdict_is_not_visible_to_the_model():
    """The private control-plane key must never reach the model, whether the
    result is returned or the failure surfaces as a raised error."""
    def boom(x: str = "") -> str:
        raise RuntimeError("network down")

    try:
        result = Agent(
            name="t", instructions="x", tools=[boom], tool_config=FAST
        ).execute_tool("boom", {})
        surfaced = str(result)
    except Exception as exc:
        surfaced = str(exc)
    assert "_praison_retryable" not in surfaced
    assert "retryable" not in surfaced


def test_async_a_tools_own_retryable_field_does_not_drive_the_retry_loop():
    """Async parity: a tool whose payload carries 'retryable' must not steer the
    async retry loop. The public execute_tool_async path (not just the impl) must
    run the body exactly once and preserve the tool-owned field."""
    calls = []

    def upstream(x: str = "") -> dict:
        calls.append(1)
        return {"error": "upstream 503", "retryable": True}

    agent = Agent(name="t", instructions="x", tools=[upstream], tool_config=FAST)
    result = asyncio.run(agent.execute_tool_async("upstream", {}))
    assert len(calls) == 1
    # The tool's own payload field survives untouched...
    assert result.get("retryable") is True
    # ...and the framework's private control key never appears on the surfaced dict.
    assert "_praison_retryable" not in result


def test_async_framework_verdict_is_not_visible_to_the_model():
    """Async parity: the private control-plane key must never reach the model on
    the public execute_tool_async path after the retry budget is exhausted."""
    def boom(x: str = "") -> str:
        raise RuntimeError("network down")

    agent = Agent(name="t", instructions="x", tools=[boom], tool_config=FAST)
    result = asyncio.run(agent.execute_tool_async("boom", {}))
    assert "_praison_retryable" not in str(result)


def test_async_breaker_opens_after_raised_exceptions():
    """A *raised* async tool exception is a breaker failure, matching the sync
    path's ``breaker.call``. Five raised failures must open the breaker so the
    sixth call short-circuits with ``circuit_open`` instead of hammering the
    flaky tool again — the exception exit previously skipped the record block.
    """
    def flaky(x: str = "") -> str:
        raise RuntimeError("upstream 503")

    agent = Agent(name="t", instructions="x", tools=[flaky])

    async def _drive():
        results = []
        for _ in range(6):
            # Call the impl directly (no retry loop) so each raised failure is
            # recorded exactly once against the breaker.
            results.append(
                await agent._execute_tool_async_impl("flaky", {}, None, None)
            )
        return results

    results = asyncio.run(_drive())
    # First five ran the tool and failed; the sixth is rejected by the breaker.
    assert results[-1].get("circuit_open") is True
    assert not any(r.get("circuit_open") for r in results[:5])


def test_async_breaker_is_per_instance():
    """One agent's open breaker must not trip a distinct agent's same-named
    tool — the breaker key is instance-scoped (``tool_{id(self)}_{name}``)."""
    def flaky(x: str = "") -> str:
        raise RuntimeError("boom")

    agent_a = Agent(name="a", instructions="x", tools=[flaky])
    agent_b = Agent(name="b", instructions="x", tools=[flaky])

    async def _open(agent):
        for _ in range(5):
            await agent._execute_tool_async_impl("flaky", {}, None, None)
        # Agent A's breaker is now open.
        return await agent._execute_tool_async_impl("flaky", {}, None, None)

    a_result = asyncio.run(_open(agent_a))
    assert a_result.get("circuit_open") is True

    # Agent B, sharing the tool name, still runs its own tool (breaker closed).
    b_first = asyncio.run(
        agent_b._execute_tool_async_impl("flaky", {}, None, None)
    )
    assert not b_first.get("circuit_open")
