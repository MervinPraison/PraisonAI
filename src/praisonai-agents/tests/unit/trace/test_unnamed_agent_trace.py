"""Unnamed agents in traces and graphs, agent_end status, and async model-call events.

Deterministic: the model call is replaced, so nothing reaches a provider.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from praisonaiagents.trace.context_events import (
    ContextListSink,
    ContextTraceEmitter,
    reset_context_emitter,
    set_context_emitter,
)


@pytest.fixture
def sink(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-used")
    s = ContextListSink()
    token = set_context_emitter(ContextTraceEmitter(sink=s, session_id="t", enabled=True))
    yield s
    reset_context_emitter(token)


def _of(sink, kind):
    return [e for e in sink.get_events() if e.event_type.value == kind]


def _fake_completion(text="Solar sails ride sunlight."):
    message = SimpleNamespace(content=text, tool_calls=None, role="assistant", reasoning_content=None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="stop", index=0)],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18),
        model="gpt-4o-mini",
    )


def search(query: str) -> str:
    """Search the web."""
    return "result"


# --- to_graph and ids ---------------------------------------------------------

def test_to_graph_accepts_an_unnamed_agent(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-used")
    from praisonaiagents import Agent
    from praisonaiagents.workflows.diagram import to_graph

    graph = to_graph(Agent(instructions="Answer briefly.", tools=[search]))
    ids = [n["id"] for n in graph["nodes"]]
    assert ids[:3] == ["start:begin", "agent:Agent", "tool:Agent/search"] or set(ids) >= {
        "start:begin", "agent:Agent", "tool:Agent/search", "end:done"}
    assert next(n for n in graph["nodes"] if n["id"] == "agent:Agent")["label"] == "Agent"


def test_named_agent_graph_is_unchanged(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-used")
    from praisonaiagents import Agent
    from praisonaiagents.workflows.diagram import to_graph

    ids = [n["id"] for n in to_graph(Agent(name="Writer", instructions="x", tools=[search]))["nodes"]]
    assert "agent:Writer" in ids and "tool:Writer/search" in ids


def test_emitter_ids_for_an_unnamed_agent():
    s = ContextListSink()
    em = ContextTraceEmitter(sink=s, session_id="t", enabled=True)
    em.agent_start(None)
    em.tool_call_start(None, "search", {"query": "x"})
    em.tool_call_end(None, "search", "ok", 1.0)
    em.agent_end(None)
    assert [e.node_id for e in s.get_events()] == [
        "agent:Agent", "tool:Agent/search", "tool:Agent/search", "agent:Agent"]


def test_unnamed_agent_run_matches_its_graph(sink):
    from praisonaiagents import Agent
    from praisonaiagents.workflows.diagram import to_graph

    agent = Agent(instructions="Answer briefly.")
    with patch.object(agent, "_chat_completion", return_value=_fake_completion()):
        agent.chat("Why do solar sails work?")
    graph_ids = {n["id"] for n in to_graph(agent)["nodes"]}
    for kind in ("agent_start", "agent_end"):
        (event,) = _of(sink, kind)
        assert event.agent_name is None  # the name is not invented on the event
        assert event.node_id == "agent:Agent" and event.node_id in graph_ids


# --- agent_end status ---------------------------------------------------------

def test_agent_end_records_completed(sink):
    from praisonaiagents import Agent

    agent = Agent(name="Writer", instructions="x")
    with patch.object(agent, "_chat_completion", return_value=_fake_completion()):
        assert agent.chat("hi")
    assert _of(sink, "agent_end")[0].data == {"status": "completed"}


def test_agent_end_records_failed(sink):
    from praisonaiagents import Agent

    agent = Agent(name="Writer", instructions="x")
    with patch.object(agent, "_chat_completion", side_effect=RuntimeError("provider down")):
        try:
            result = agent.chat("hi")
        except Exception:
            result = None
    assert result is None
    assert _of(sink, "agent_end")[0].data == {"status": "failed"}


# --- async model calls --------------------------------------------------------

def test_astart_records_the_model_call(sink):
    from praisonaiagents import Agent

    agent = Agent(name="Writer", instructions="x", llm="gpt-4o-mini")

    async def fake_dispatch(*args, **kwargs):
        return _fake_completion()

    with patch.object(agent, "_achat_completion_with_retry_dispatch", side_effect=fake_dispatch):
        answer = asyncio.run(agent.astart("Why do solar sails work?"))
    assert "sunlight" in str(answer)
    (req,) = _of(sink, "llm_request")
    (resp,) = _of(sink, "llm_response")
    assert req.node_id == resp.node_id == "agent:Writer"
    assert resp.prompt_tokens == 11 and resp.completion_tokens == 7 and resp.cost_usd > 0
    assert "sunlight" in (resp.data.get("response_content") or "")
    assert _of(sink, "agent_end")[0].data == {"status": "completed"}


def test_async_model_error_is_recorded(sink):
    from praisonaiagents import Agent

    agent = Agent(name="Writer", instructions="x", llm="gpt-4o-mini")

    async def boom(*args, **kwargs):
        raise RuntimeError("rate limited")

    with patch.object(agent, "_achat_completion_with_retry_dispatch", side_effect=boom):
        try:
            asyncio.run(agent.astart("hi"))
        except Exception:
            pass
    responses = _of(sink, "llm_response")
    assert responses and responses[0].data.get("finish_reason") == "error"
    assert "rate limited" in (responses[0].data.get("response_content") or "")


def test_async_path_records_nothing_when_tracing_is_off(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-used")
    from praisonaiagents import Agent

    s = ContextListSink()
    token = set_context_emitter(ContextTraceEmitter(sink=s, session_id="t", enabled=False))
    try:
        agent = Agent(name="Writer", instructions="x", llm="gpt-4o-mini")

        async def fake_dispatch(*args, **kwargs):
            return _fake_completion()

        with patch.object(agent, "_achat_completion_with_retry_dispatch", side_effect=fake_dispatch) as d:
            asyncio.run(agent.astart("hi"))
        assert d.called and s.get_events() == []
    finally:
        reset_context_emitter(token)


# --- streamed turns (start(stream=True)) ---------------------------------------

def _fake_stream(self, prompt, **kwargs):
    yield "Solar "
    yield "sails."


def test_streamed_turn_records_agent_start_and_end(sink):
    from praisonaiagents import Agent

    agent = Agent(instructions="x")
    with patch.object(type(agent), "_start_stream_turn", _fake_stream):
        text = "".join(agent._start_stream("hi"))
    assert text == "Solar sails."
    kinds = [(e.event_type.value, e.node_id, e.data.get("status")) for e in sink.get_events()]
    assert kinds == [("agent_start", "agent:Agent", None), ("agent_end", "agent:Agent", "completed")]


def test_streamed_turn_stopped_early_is_cancelled(sink):
    from praisonaiagents import Agent

    agent = Agent(name="Writer", instructions="x")
    with patch.object(type(agent), "_start_stream_turn", _fake_stream):
        gen = agent._start_stream("hi")
        next(gen)
        gen.close()  # the page stopped reading
    assert _of(sink, "agent_end")[0].data == {"status": "cancelled"}


def test_streamed_turn_that_raises_is_failed(sink):
    from praisonaiagents import Agent

    def boom(self, prompt, **kwargs):
        yield "x"
        raise RuntimeError("provider down")

    agent = Agent(name="Writer", instructions="x")
    with patch.object(type(agent), "_start_stream_turn", boom):
        with pytest.raises(RuntimeError):
            list(agent._start_stream("hi"))
    assert _of(sink, "agent_end")[0].data == {"status": "failed"}


def test_streamed_turn_records_nothing_when_tracing_is_off(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-used")
    from praisonaiagents import Agent

    s = ContextListSink()
    token = set_context_emitter(ContextTraceEmitter(sink=s, session_id="t", enabled=False))
    try:
        agent = Agent(name="Writer", instructions="x")
        with patch.object(type(agent), "_start_stream_turn", _fake_stream):
            assert "".join(agent._start_stream("hi")) == "Solar sails."
        assert s.get_events() == []
    finally:
        reset_context_emitter(token)
