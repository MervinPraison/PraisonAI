"""``ExecutionConfig.max_execution_time`` and ``run_autonomous(timeout_seconds=)`` (#6029).

Both caps become a deadline on the turn's cancel token, so the LLM tool loop
stops at its next boundary instead of running to completion.
``litellm.completion`` is stubbed; nothing leaves the machine.
"""
import asyncio
import time

import pytest

pytest.importorskip("litellm")

from praisonaiagents import Agent  # noqa: E402
from praisonaiagents.config.feature_configs import ExecutionConfig  # noqa: E402
from praisonaiagents.escalation.loop_guard import LoopGuardConfig  # noqa: E402

MODEL = "anthropic/claude-3-5-sonnet-20240620"
USAGE = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}


@pytest.fixture
def calls(monkeypatch):
    """Stub litellm so the model asks for ``slow_step`` on every call."""
    # Import here, not at module level: other tests evict ``litellm`` from
    # sys.modules, and LLM then imports a fresh module object at call time.
    import litellm
    from litellm import ModelResponse

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    # Agent caches its env-derived default model per process; keep the fake
    # key's Anthropic default from leaking into later tests.
    monkeypatch.setattr(Agent, "_default_model", None)
    monkeypatch.setattr(Agent, "_default_model_checked", False)
    state = {"n": 0}

    def fake(*a, **k):
        state["n"] += 1
        if not k.get("tools"):
            return ModelResponse(model=k.get("model"), usage=USAGE, choices=[{
                "index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": "done"}}])
        return ModelResponse(model=k.get("model"), usage=USAGE, choices=[{
            "index": 0, "finish_reason": "tool_calls",
            "message": {"role": "assistant", "content": None, "tool_calls": [{
                "id": f"call_{state['n']}", "type": "function",
                "function": {"name": "slow_step", "arguments": "{}"}}]}}])

    async def afake(*a, **k):
        return fake(*a, **k)

    monkeypatch.setattr(litellm, "completion", fake)
    monkeypatch.setattr(litellm, "acompletion", afake)
    return state


def slow_step() -> str:
    """A slow step."""
    time.sleep(0.4)
    return "ok"


def _agent(**kw):
    return Agent(name="t", instructions="x", llm=MODEL, tools=[slow_step],
                 output="silent", **kw)


def test_max_execution_time_stops_tool_loop(calls):
    agent = _agent(execution=ExecutionConfig(max_execution_time=1, max_iter=50))
    t0 = time.time()
    out = agent.chat("go")
    elapsed = time.time() - t0
    assert elapsed < 3
    assert "timeout" in (out or "")
    assert agent.last_stop_reason == "timeout"
    assert calls["n"] < 10


def test_max_execution_time_stops_tool_loop_async(calls):
    agent = _agent(execution=ExecutionConfig(max_execution_time=1, max_iter=50))
    t0 = time.time()
    out = asyncio.run(agent.achat("go"))
    assert time.time() - t0 < 3
    assert "timeout" in (out or "")
    assert agent.last_stop_reason == "timeout"


def test_unset_max_execution_time_creates_no_deadline():
    agent = Agent(name="t", instructions="x", output="silent")
    assert agent._turn_cancel_token(None, explicit=False) is None


def test_loop_guard_turn_limit_follows_max_execution_time():
    agent = Agent(name="t", instructions="x", output="silent",
                  execution=ExecutionConfig(max_execution_time=600))
    assert agent._ensure_loop_guard().config.max_time_per_turn == 600
    default = Agent(name="d", instructions="x", output="silent")
    assert default._ensure_loop_guard().config.max_time_per_turn == LoopGuardConfig.max_time_per_turn


def test_run_autonomous_timeout_bounds_the_running_turn(calls):
    agent = _agent(autonomy=True, execution=ExecutionConfig(max_iter=50))
    t0 = time.time()
    result = agent.run_autonomous("go", max_iterations=1, timeout_seconds=1)
    assert time.time() - t0 < 3
    assert result.completion_reason == "timeout"
    assert not result.success


def test_run_autonomous_async_timeout_bounds_the_running_turn(calls):
    agent = _agent(autonomy=True, execution=ExecutionConfig(max_iter=50))
    t0 = time.time()
    result = asyncio.run(agent.run_autonomous_async("go", max_iterations=1, timeout_seconds=1))
    assert time.time() - t0 < 3
    assert result.completion_reason == "timeout"


def test_run_autonomous_reports_turn_max_execution_time(calls):
    """A turn cut by max_execution_time is a failed timeout, not a goal."""
    agent = _agent(autonomy=True, execution=ExecutionConfig(max_execution_time=1, max_iter=50))
    result = agent.run_autonomous("go", max_iterations=3)
    assert result.completion_reason == "timeout"
    assert not result.success
    result = asyncio.run(agent.run_autonomous_async("go", max_iterations=3))
    assert result.completion_reason == "timeout"
    assert not result.success
