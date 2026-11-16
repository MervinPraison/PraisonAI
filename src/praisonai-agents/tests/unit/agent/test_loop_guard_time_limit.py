"""Loop guard per-turn time limit is configurable via ExecutionConfig (#6026)."""
import asyncio

import pytest

import praisonaiagents.escalation.loop_guard as lg
from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import ExecutionConfig
from praisonaiagents.escalation.loop_guard import GuardAction, LoopGuardConfig
from praisonaiagents.model_harness import ScriptedModel


@pytest.fixture
def clock(monkeypatch):
    state = {"t": 1_000_000.0}

    class FakeTime:
        @staticmethod
        def time():
            return state["t"]

    monkeypatch.setattr(lg, "time", FakeTime)
    return state


def _agent(clock, tool_seconds, execution=None, calls=None):
    calls = [] if calls is None else calls

    def run_tests(suite: str) -> str:
        """Run a (slow) test suite."""
        calls.append(suite)
        clock["t"] += tool_seconds
        return f"{suite}: 412 passed"

    model = ScriptedModel([
        ScriptedModel.tool_call("run_tests", {"suite": "unit"}),
        ScriptedModel.tool_call("run_tests", {"suite": "integration"}),
        "All suites passed.",
    ])
    kwargs = {"execution": execution} if execution is not None else {}
    return Agent(name="coder", instructions="Run the tests.", llm=model,
                 tools=[run_tests], output="silent", **kwargs)


@pytest.mark.parametrize("use_async", [False, True])
def test_default_turn_with_130s_tool_completes(clock, use_async):
    agent = _agent(clock, 130.0)
    if use_async:
        out = asyncio.run(agent.achat("Run both suites"))
    else:
        out = agent.chat("Run both suites")
    assert "All suites passed" in str(out)


@pytest.mark.parametrize("use_async", [False, True])
def test_configured_limit_halts(clock, use_async):
    calls = []
    agent = _agent(clock, 130.0, ExecutionConfig(max_execution_time=60), calls)
    if use_async:
        asyncio.run(agent.achat("Run both suites"))
    else:
        with pytest.raises(Exception, match="Turn time limit exceeded"):
            agent.chat("Run both suites")
    # The second tool call is refused by the loop guard on both paths.
    assert calls == ["unit"]


@pytest.mark.parametrize("use_async", [False, True])
def test_zero_disables_time_halt(clock, use_async):
    agent = _agent(clock, 10_000.0, ExecutionConfig(max_execution_time=0))
    if use_async:
        out = asyncio.run(agent.achat("Run both suites"))
    else:
        out = agent.chat("Run both suites")
    assert "All suites passed" in str(out)


def test_ensure_loop_guard_reads_max_execution_time():
    agent = Agent(name="a", instructions="x", llm=ScriptedModel(["ok"]),
                  output="silent", execution=ExecutionConfig(max_execution_time=900))
    assert agent._ensure_loop_guard().config.max_time_per_turn == 900.0


def test_real_loop_still_halts_without_time_limit():
    guard = lg.LoopGuard(LoopGuardConfig(max_time_per_turn=float("inf")))
    actions = []
    for _ in range(20):
        decision = guard.check("read_file", {"path": "a.txt"})
        actions.append(decision.action)
        if decision.action == GuardAction.HALT:
            break
        guard.record("read_file", {"path": "a.txt"}, success=True, result="same")
    assert actions[-1] == GuardAction.HALT
