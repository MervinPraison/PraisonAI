"""Regression tests for #6631.

1. Guardrail retry works on the custom-LLM (litellm) path and keeps the system prompt.
2. Tools passed per-turn (``Task(tools=...)`` / ``chat(tools=...)``) are dispatchable.
3. Session history: achat() persists/resumes, memory="history" does not double-send,
   and ephemeral() turns are never persisted.
"""
import asyncio
import json

import pytest

litellm = pytest.importorskip("litellm")

from praisonaiagents import Agent, AgentTeam, MemoryConfig, Task  # noqa: E402

LLM = "anthropic/claude-3-5-sonnet-20240620"


def _resp(content=None, tool=None):
    msg = {"role": "assistant", "content": content}
    if tool:
        msg["tool_calls"] = [{
            "id": "c1", "type": "function",
            "function": {"name": tool[0], "arguments": json.dumps(tool[1])},
        }]
    return litellm.ModelResponse(choices=[{"message": msg, "finish_reason": "tool_calls" if tool else "stop"}])


@pytest.fixture
def scripted(monkeypatch):
    calls = []

    def install(seq):
        it = iter(seq)

        def f(**kw):
            calls.append(kw)
            return next(it)

        async def af(**kw):
            calls.append(kw)
            return next(it)

        monkeypatch.setattr(litellm, "completion", f)
        monkeypatch.setattr(litellm, "acompletion", af)
        return calls

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    return install


def _must_cite(output):
    ok = "FACT-" in output.raw
    return ok, output.raw if ok else "answer must cite a FACT id"


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_guardrail_retry_custom_llm(scripted, mode):
    calls = scripted([_resp("42"), _resp("Per FACT-123 it is 42")])
    a = Agent(name="A", instructions="Answer in French.", llm=LLM, guardrails=_must_cite, output="silent")
    a._guardrail_retry_delay = lambda n: 0
    out = a.chat("What?") if mode == "sync" else asyncio.run(a.achat("What?"))
    assert out == "Per FACT-123 it is 42"
    assert len(calls) == 2
    assert calls[1]["messages"][0]["role"] == "system"


def test_completion_text_shapes():
    from types import SimpleNamespace as NS
    assert Agent._completion_text("x") == "x"
    assert Agent._completion_text({"choices": [{"message": {"content": "d"}}]}) == "d"
    obj = NS(choices=[NS(message=NS(content="o"))])
    assert Agent._completion_text(obj) == "o"
    with pytest.raises(Exception):
        Agent._completion_text({"choices": []})


RAN = []


def get_weather(city: str) -> str:
    """Get weather"""
    RAN.append(city)
    return f"sunny in {city}"


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_task_tools_dispatch(scripted, mode):
    RAN.clear()
    scripted([_resp(tool=("get_weather", {"city": "Paris"})), _resp("done")])
    a = Agent(name="A", instructions="x", llm=LLM, output="silent")
    t = Task(description="weather in Paris", expected_output="weather", agent=a, tools=[get_weather])
    team = AgentTeam(agents=[a], tasks=[t], output="silent")
    team.start() if mode == "sync" else asyncio.run(team.astart())
    assert RAN == ["Paris"]


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_chat_tools_dispatch(scripted, mode):
    RAN.clear()
    scripted([_resp(tool=("get_weather", {"city": "Rome"})), _resp("done")])
    a = Agent(name="B", instructions="x", llm=LLM, output="silent")
    a.chat("w", tools=[get_weather]) if mode == "sync" else asyncio.run(a.achat("w", tools=[get_weather]))
    assert RAN == ["Rome"]


# --- session history -------------------------------------------------------

@pytest.fixture
def history_agent(tmp_path, monkeypatch):
    from praisonaiagents.session.store import DefaultSessionStore

    store = DefaultSessionStore(session_dir=str(tmp_path))
    requests = []

    def make(sid=None, memory=None):
        a = Agent(name="bot", instructions="x", llm="gpt-4o-mini", output="silent",
                  memory=memory or MemoryConfig(session_id=sid, user_id="u"))
        a._session_store = store

        def f(messages, *args, **kw):
            requests.append([m["content"] for m in messages if m["role"] != "system"])
            last = [m for m in messages if m["role"] == "user"][-1]["content"]
            return litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content": f"ans-{last}"}, "finish_reason": "stop"}])

        async def af(messages, *args, **kw):
            return f(messages)

        a._chat_completion = f
        a._achat_completion_with_retry = af
        return a

    monkeypatch.setenv("OPENAI_API_KEY", "x")
    return make, requests, store


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_session_resume_parity(history_agent, mode):
    make, requests, store = history_agent
    run = (lambda a, p: a.chat(p)) if mode == "sync" else (lambda a, p: asyncio.run(a.achat(p)))
    run(make("s"), "my name is Ada")
    assert [m["content"] for m in store.get_chat_history("s")] == ["my name is Ada", "ans-my name is Ada"]
    run(make("s"), "what is my name?")
    assert requests[-1] == ["my name is Ada", "ans-my name is Ada", "what is my name?"]


def test_history_memory_not_double_sent(history_agent):
    make, requests, _ = history_agent
    a = make(memory="history")
    a.chat("q1")
    a.chat("q2")
    assert requests[-1] == ["q1", "ans-q1", "q2"]
    b = make(memory="history")
    b.chat("q3")
    assert requests[-1] == ["q1", "ans-q1", "q2", "ans-q2", "q3"]


def test_ephemeral_not_persisted(history_agent):
    make, requests, store = history_agent
    a = make("e")
    a.chat("A")
    with a.ephemeral():
        a.chat("SECRET")
    a.chat("B")
    assert "SECRET" not in requests[-1]
    assert [m["content"] for m in store.get_chat_history("e")] == ["A", "ans-A", "B", "ans-B"]
