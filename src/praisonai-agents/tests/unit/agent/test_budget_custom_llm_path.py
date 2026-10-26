"""Budget and cost accounting on the custom-LLM (``provider/model``) path (#6029).

That path hands the whole turn, tool loop included, to ``LLM.get_response*``.
Every call it makes must reach the Agent's cost/token counters so
``ExecutionConfig.max_budget`` and the autonomy spend caps can fire.
``litellm.completion`` is stubbed; nothing leaves the machine.
"""
import asyncio

import pytest

pytest.importorskip("litellm")

from praisonaiagents import Agent  # noqa: E402
from praisonaiagents.config.feature_configs import ExecutionConfig  # noqa: E402
from praisonaiagents.errors import BudgetExceededError  # noqa: E402

MODEL = "anthropic/claude-3-5-sonnet-20240620"
USAGE = {"prompt_tokens": 1500, "completion_tokens": 1500, "total_tokens": 3000}


def _litellm():
    """The litellm module LLM will import now.

    Other tests evict ``litellm`` from sys.modules, so a module-level binding
    can go stale and stubbing it would let the real client run.
    """
    import litellm
    return litellm


def _text(model):
    return _litellm().ModelResponse(model=model, usage=USAGE, choices=[{
        "index": 0, "finish_reason": "stop",
        "message": {"role": "assistant", "content": "ok"}}])


def _tool_call(model, n):
    return _litellm().ModelResponse(model=model, usage=USAGE, choices=[{
        "index": 0, "finish_reason": "tool_calls",
        "message": {"role": "assistant", "content": None, "tool_calls": [{
            "id": f"call_{n}", "type": "function",
            "function": {"name": "step", "arguments": "{}"}}]}}])


@pytest.fixture
def calls(monkeypatch):
    """Stub litellm; answer with a tool call while ``tool_rounds`` remain."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    state = {"n": 0, "tool_rounds": 0}

    def fake(*a, **k):
        state["n"] += 1
        if k.get("tools") and state["tool_rounds"] > 0:
            state["tool_rounds"] -= 1
            return _tool_call(k.get("model"), state["n"])
        return _text(k.get("model"))

    async def afake(*a, **k):
        return fake(*a, **k)

    litellm = _litellm()
    monkeypatch.setattr(litellm, "completion", fake)
    monkeypatch.setattr(litellm, "acompletion", afake)
    return state


def _agent(**kw):
    return Agent(name="p", instructions="x", llm=MODEL, output="silent", **kw)


def step() -> str:
    """One step of work."""
    return "done"


def test_sync_chat_counts_cost_and_tokens(calls):
    agent = _agent()
    assert agent.chat("hi") == "ok"
    summary = agent.cost_summary
    assert summary["llm_calls"] == 1
    assert summary["tokens_in"] == 1500 and summary["tokens_out"] == 1500
    assert agent.total_cost > 0


def test_sync_budget_raises_between_turns(calls):
    agent = _agent(execution=ExecutionConfig(max_budget=0.05))
    with pytest.raises(BudgetExceededError):
        for i in range(5):
            agent.chat(f"hello {i}")
    assert calls["n"] < 5
    assert agent.total_cost >= 0.05


def test_async_budget_raises_between_turns(calls):
    agent = _agent(execution=ExecutionConfig(max_budget=0.05))

    async def run():
        for i in range(5):
            await agent.achat(f"hello {i}")

    with pytest.raises(BudgetExceededError):
        asyncio.run(run())
    assert calls["n"] < 5
    assert agent.total_cost >= 0.05


def test_budget_trips_mid_tool_loop(calls):
    calls["tool_rounds"] = 10  # the model would keep calling tools for 11 calls
    agent = _agent(execution=ExecutionConfig(max_budget=1.0))
    agent.chat("price one call")
    one_call = agent.total_cost
    calls["n"] = 0
    # A cap between one and two calls must stop the loop at the second call.
    agent = _agent(tools=[step], execution=ExecutionConfig(max_budget=one_call * 1.5))
    with pytest.raises(BudgetExceededError):
        agent.chat("go")
    assert calls["n"] == 2


def test_warn_mode_does_not_raise(calls):
    agent = _agent(execution=ExecutionConfig(max_budget=0.001, on_budget_exceeded="warn"))
    assert agent.chat("hi") == "ok"
    assert agent.total_cost > 0.001


def test_autonomy_budget_exhausted_on_provider_path(calls):
    agent = _agent(autonomy={"max_budget_usd": 0.001})
    result = agent.run_autonomous("go", max_iterations=3)
    assert result.completion_reason == "budget_exhausted"
    assert calls["n"] == 1


def test_sink_ignores_other_llm_instances(calls):
    """A call made by a different LLM object is not billed to this agent."""
    from praisonaiagents.llm.llm import LLM

    agent = _agent()
    other = LLM(model=MODEL)
    with agent._llm_usage_sink():
        other._track_token_usage(_text(MODEL), MODEL)
    assert agent.cost_summary["llm_calls"] == 0


def test_retry_after_exhaustion_sends_no_request(calls):
    agent = _agent(execution=ExecutionConfig(max_budget=0.001))
    with pytest.raises(BudgetExceededError):
        agent.chat("first")
    sent = calls["n"]
    with pytest.raises(BudgetExceededError):
        agent.chat("retry")
    with pytest.raises(BudgetExceededError):
        asyncio.run(agent.achat("retry async"))
    assert calls["n"] == sent


def test_autonomy_budget_error_keeps_budget_exhausted(calls):
    """A max_budget stop inside the turn still reports the autonomy cap result."""
    agent = _agent(execution=ExecutionConfig(max_budget=0.001),
                   autonomy={"max_budget_usd": 0.001})
    result = agent.run_autonomous("go", max_iterations=3)
    assert result.completion_reason == "budget_exhausted"
    result = asyncio.run(_agent(execution=ExecutionConfig(max_budget=0.001),
                                autonomy={"max_budget_usd": 0.001}).run_autonomous_async("go", max_iterations=3))
    assert result.completion_reason == "budget_exhausted"
