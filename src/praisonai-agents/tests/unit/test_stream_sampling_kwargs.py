"""max_tokens and top_p passed to Agent.start(stream=True) must reach the request.

Both knobs travelled the same route as temperature -- collected by the desktop,
validated, persisted, echoed by GET /settings, forwarded into
agent.start(**kwargs) -- and were then dropped: the streaming request was built
from model / messages / temperature / stream only. temperature arrived, which is
what made this a silent drop rather than a dead channel.

The tests stub the transport and assert the kwargs the transport receives.
"""
import os

import pytest

from praisonaiagents import Agent


class _Delta:
    content = None
    tool_calls = None


class _Chunk:
    def __init__(self):
        d = _Delta(); d.content = "ok"
        self.choices = [type("C", (), {"delta": d, "finish_reason": "stop"})()]


class _RecordingOpenAI:
    """A proxy over the real client wrapper: everything (build_messages, ...)
    is delegated; only the transport call is intercepted and recorded."""
    def __init__(self, real):
        self._real = real
        self.calls = []
        outer = self
        class _Completions:
            def create(self, **kw):
                outer.calls.append(kw)
                return iter([_Chunk()])
        class _Chat:
            completions = _Completions()
        class _Sync:
            chat = _Chat()
        self.sync_client = _Sync()
    def __getattr__(self, name):
        return getattr(self._real, name)


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    a = Agent(name="t", instructions="x", llm="gpt-4o-mini")
    from praisonaiagents.llm import get_openai_client
    stub = _RecordingOpenAI(get_openai_client(api_key="sk-test"))
    a._Agent__openai_client = stub            # the lazily-built client, pre-seeded
    return a, stub


def _drain(gen):
    return "".join(gen)


def test_openai_stream_forwards_max_tokens_and_top_p(agent):
    a, stub = agent
    _drain(a.start("hi", stream=True, max_tokens=7, top_p=0.5))
    assert stub.calls, "the stub transport was never called"
    kw = stub.calls[0]
    assert kw.get("max_tokens") == 7, kw
    assert kw.get("top_p") == 0.5, kw


def test_openai_stream_omits_knobs_that_were_not_given(agent):
    """Present-only: an unset knob must stay OUT of the payload."""
    a, stub = agent
    _drain(a.start("hi", stream=True))
    kw = stub.calls[0]
    assert "max_tokens" not in kw and "top_p" not in kw, kw


def test_custom_llm_stream_forwards_knobs_without_clobbering(monkeypatch):
    """The LiteLLM branch merges with params.update(); None must never be sent."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    a = Agent(name="t", instructions="x", llm="openai/gpt-4o-mini")
    seen = {}
    def fake_stream(**kw):
        seen.update(kw); yield "ok"
    a.llm_instance.get_response_stream = fake_stream
    _drain(a.start("hi", stream=True, max_tokens=9))
    assert seen.get("max_tokens") == 9
    assert "top_p" not in seen, "top_p was not given and must not be forwarded as None"
