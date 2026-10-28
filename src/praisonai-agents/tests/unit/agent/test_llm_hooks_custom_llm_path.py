"""BEFORE_LLM / AFTER_LLM on the custom-LLM (``provider/model``) path (#5821).

That path hands the turn to ``LLM.get_response*`` and skips
``_chat_completion``, so it must fire the same hooks itself, once per turn,
with ``tokens_used`` taken from the provider's ``usage``.
``litellm.completion`` is stubbed; nothing leaves the machine.
"""
import asyncio

import pytest

pytest.importorskip("litellm")

from praisonaiagents import Agent  # noqa: E402
from praisonaiagents.hooks import HookEvent, HookRegistry, HookResult  # noqa: E402

MODEL = "anthropic/claude-3-5-sonnet-20240620"


def _litellm():
    import litellm
    return litellm


def _response(model, n, tool_call=False):
    message = {"role": "assistant", "content": "ok"}
    if tool_call:
        message = {"role": "assistant", "content": None, "tool_calls": [{
            "id": f"call_{n}", "type": "function",
            "function": {"name": "step", "arguments": "{}"}}]}
    usage = {"prompt_tokens": 100 + n, "completion_tokens": 10 + n,
             "total_tokens": 110 + 2 * n}
    return _litellm().ModelResponse(model=model, usage=usage, choices=[{
        "index": 0, "finish_reason": "tool_calls" if tool_call else "stop",
        "message": message}])


@pytest.fixture
def calls(monkeypatch):
    """Stub litellm; answer with a tool call while ``tool_rounds`` remain."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(Agent, "_default_model", None)
    monkeypatch.setattr(Agent, "_default_model_checked", False)
    state = {"n": 0, "tool_rounds": 0, "messages": []}

    def fake(*a, **k):
        state["n"] += 1
        state["messages"].append(k.get("messages"))
        if k.get("tools") and state["tool_rounds"] > 0:
            state["tool_rounds"] -= 1
            return _response(k.get("model"), state["n"], tool_call=True)
        return _response(k.get("model"), state["n"])

    async def afake(*a, **k):
        return fake(*a, **k)

    litellm = _litellm()
    monkeypatch.setattr(litellm, "completion", fake)
    monkeypatch.setattr(litellm, "acompletion", afake)
    return state


def _agent(registry, **kw):
    return Agent(name="p", instructions="x", llm=MODEL, output="silent",
                 hooks=registry, **kw)


def _recorder():
    registry, seen = HookRegistry(), []
    for event in (HookEvent.BEFORE_LLM, HookEvent.AFTER_LLM):
        registry.register_function(event, lambda data: seen.append(data) or HookResult.allow())
    return registry, seen


def step() -> str:
    """One step of work."""
    return "done"


@pytest.mark.parametrize("run", [
    lambda a: a.chat("hi"),
    lambda a: asyncio.run(a.achat("hi")),
], ids=["sync", "async"])
def test_hooks_fire_with_provider_tokens(calls, run):
    registry, seen = _recorder()
    assert run(_agent(registry)) == "ok"
    assert [e.event_name for e in seen] == [HookEvent.BEFORE_LLM, HookEvent.AFTER_LLM]
    before, after = seen
    assert before.model == MODEL and before.messages[-1]["content"] == "hi"
    assert after.tokens_used == 101 + 11
    assert after.response == "ok"


def test_tokens_cover_every_call_in_a_tool_round_trip(calls):
    calls["tool_rounds"] = 1
    registry, seen = _recorder()
    assert _agent(registry, tools=[step]).chat("go") == "ok"
    after = [e for e in seen if e.event_name == HookEvent.AFTER_LLM]
    assert len(after) == 1  # Same once-per-turn granularity as the OpenAI-client path.
    assert after[0].tokens_used == (101 + 11) + (102 + 12)


def test_blocking_before_llm_skips_the_provider(calls):
    registry = HookRegistry()
    registry.register_function(HookEvent.BEFORE_LLM, lambda data: HookResult.deny("nope"))
    result = _agent(registry).chat("hi")
    assert calls["n"] == 0
    assert "nope" in result


def test_before_llm_message_rewrite_reaches_the_provider(calls):
    registry = HookRegistry()

    def redact(data):
        messages = [{**m, "content": str(m["content"]).replace("my secret", "[redacted]")}
                    for m in data.messages]
        return HookResult(decision="allow", modified_input={"messages": messages})

    registry.register_function(HookEvent.BEFORE_LLM, redact, sequential=True)
    assert _agent(registry).chat("my secret") == "ok"
    sent = calls["messages"][0]
    assert sent[0]["role"] == "system"
    assert all("my secret" not in str(m.get("content")) for m in sent)
    assert any(m.get("content") == "[redacted]" for m in sent)
