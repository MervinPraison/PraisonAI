"""Tool guards on a shared Agent must not punish the wrong caller (issue #5860).

1. Each chat turn gets its own loop guard, so overlapping turns never exhaust
   each other's per-turn limits.
2. Caller errors (ValueError/TypeError/AttributeError from bad input) do not
   open the tool circuit breaker for every other caller; real failures still do.
"""

import asyncio
import threading

import pytest


@pytest.fixture
def agent_factory(monkeypatch):
    from praisonaiagents import Agent

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def make(tools):
        return Agent(name="shared", instructions="x", tools=tools, llm="gpt-4o-mini")

    return make


def _lookup(path: str) -> str:
    """Read something (distinct path each call)."""
    return f"read {path}"


def test_overlapping_turns_get_independent_loop_guards(agent_factory):
    from praisonaiagents.agent.chat_mixin import _enter_turn, _exit_turn

    agent = agent_factory([_lookup])
    agent_guard = agent._ensure_loop_guard()
    outer = _enter_turn(agent, None)  # a long-running turn stays in flight
    try:
        outer_guard = agent._ensure_loop_guard()
        assert outer_guard is not agent_guard
        assert outer_guard.config is agent_guard.config
        outer_guard.record("lookup", {"q": "x"}, True, "same")

        seen = {}

        def other_turn():
            tok = _enter_turn(agent, None)
            try:
                seen["guard"] = agent._ensure_loop_guard()
            finally:
                _exit_turn(agent, tok)

        th = threading.Thread(target=other_turn)
        th.start()
        th.join(5)
        assert seen["guard"] is not outer_guard
        assert seen["guard"]._tool_counts == {}
        assert outer_guard._tool_counts == {"lookup": 1}
    finally:
        _exit_turn(agent, outer)
    # Outside a turn the agent-level guard is used, as before.
    assert agent._ensure_loop_guard() is agent_guard


def test_many_overlapping_turns_are_not_halted(agent_factory):
    from praisonaiagents.agent.chat_mixin import _enter_turn, _exit_turn

    agent = agent_factory([_lookup])
    agent._ensure_loop_guard()
    tokens = []
    try:
        for i in range(20):  # 20 concurrent turns, one tool call each
            tokens.append(_enter_turn(agent, None))
            result = agent.execute_tool("_lookup", {"path": f"/tmp/{i}"})
            assert result == f"read /tmp/{i}"
    finally:
        for tok in reversed(tokens):
            _exit_turn(agent, tok)


def _get_order(order_id: str) -> str:
    """Look up an order. Raises for unknown ids."""
    if not order_id.startswith("A"):
        raise ValueError(f"unknown order {order_id}")
    return f"order {order_id}: shipped"


def _down(x: str) -> str:
    """A tool whose dependency is down."""
    raise RuntimeError("dependency down")


def _sync_run(agent, name, args):
    try:
        return agent.execute_tool(name, args)
    except Exception as e:  # surfaced ToolExecutionError
        return str(e)


def _async_run(agent, name, args):
    try:
        return asyncio.run(agent.execute_tool_async(name, args))
    except Exception as e:
        return str(e)


@pytest.mark.parametrize("run", [_sync_run, _async_run], ids=["sync", "async"])
def test_bad_input_does_not_open_circuit_breaker(agent_factory, run):
    agent = agent_factory([_get_order])
    agent._ensure_loop_guard().config.enabled = False
    for i in range(6):
        run(agent, "_get_order", {"order_id": f"bad{i}"})
    assert run(agent, "_get_order", {"order_id": "A100"}) == "order A100: shipped"


@pytest.mark.parametrize("run", [_sync_run, _async_run], ids=["sync", "async"])
def test_real_failures_still_open_circuit_breaker(agent_factory, run):
    agent = agent_factory([_down])
    agent._ensure_loop_guard().config.enabled = False
    for _ in range(6):
        result = run(agent, "_down", {"x": "1"})
    assert "circuit breaker open" in str(result)
