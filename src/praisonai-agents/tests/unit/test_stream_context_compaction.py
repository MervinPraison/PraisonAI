"""The streaming entry point must run context compaction (Issue #4714).

Agent auto-enables a ContextManager whenever tools are present (auto_compact,
compact_threshold 0.8). The non-streaming ``chat()`` path runs
``_apply_context_management`` between building the messages and issuing the
request; ``start(stream=True)`` built the same messages and sent them
unmodified, so a long session streamed the entire history to the model every
turn while the manager sat idle. The desktop's default agent has tools, so it
hit this on every streamed turn.

These tests stub the transport and assert the EFFECT: the message list that
actually reaches the transport is bounded when a ContextManager is configured,
and untouched when it is not.
"""
import pytest

from praisonaiagents import Agent


SEEDED = 400  # ~160k estimated tokens; well past 80% of gpt-4o-mini's 128k window
FILLER = "lorem ipsum dolor sit amet " * 60


def _add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


class _RecordingOpenAI:
    """A proxy over the real client wrapper: everything (build_messages, tool
    formatting, ...) is delegated; only the transport call is intercepted and
    recorded. ``iter([])`` is an empty stream -- no answer, no tool calls."""

    def __init__(self, real):
        self._real = real
        self.calls = []
        outer = self

        class _Completions:
            def create(self, **kw):
                outer.calls.append(kw)
                return iter([])

        class _Chat:
            completions = _Completions()

        class _Sync:
            chat = _Chat()

        self.sync_client = _Sync()

    def __getattr__(self, name):
        return getattr(self._real, name)


def _seed_history(agent, n=SEEDED):
    for i in range(n):
        agent.chat_history.append({
            "role": "user" if i % 2 == 0 else "assistant",
            "content": f"msg {i} {FILLER}",
        })


def _stub_openai(agent):
    from praisonaiagents.llm import get_openai_client
    stub = _RecordingOpenAI(get_openai_client(api_key="sk-test"))
    agent._Agent__openai_client = stub  # the lazily-built client, pre-seeded
    return stub


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def test_openai_stream_compacts_long_history():
    agent = Agent(name="t", instructions="x", llm="gpt-4o-mini", tools=[_add])
    assert agent.context_manager is not None, "tools present must auto-enable a ContextManager"
    _seed_history(agent)
    stub = _stub_openai(agent)

    "".join(agent.start("x", stream=True))

    assert stub.calls, "the stub transport was never called"
    sent = stub.calls[0]["messages"]
    # Far fewer than seeded: compaction at threshold 0.8 keeps the window
    # under budget, not merely one message under the seed count.
    assert len(sent) <= SEEDED * 0.7, (
        f"streamed request carried {len(sent)} messages for {SEEDED} seeded; "
        "context compaction did not run on the streaming path"
    )
    # Compaction must not lose the request itself.
    assert sent[0]["role"] == "system"
    assert sent[-1] == {"role": "user", "content": "x"}


def test_openai_stream_without_context_manager_sends_full_history():
    """Zero-overhead contract: context=False leaves the streamed request alone.

    Also pins that the bounded count above is compaction and not some other
    trimming in the streaming path."""
    agent = Agent(name="t", instructions="x", llm="gpt-4o-mini", tools=[_add], context=False)
    assert agent.context_manager is None
    _seed_history(agent)
    stub = _stub_openai(agent)

    "".join(agent.start("x", stream=True))

    sent = stub.calls[0]["messages"]
    assert len(sent) == SEEDED + 2  # system + seeded history + new user turn


def test_custom_llm_stream_compacts_long_history():
    """The LiteLLM branch passes chat_history rather than a built messages list;
    compaction must apply to the history that is actually sent."""
    agent = Agent(name="t", instructions="x", llm="openai/gpt-4o-mini", tools=[_add])
    assert agent.context_manager is not None
    _seed_history(agent)

    seen = {}

    def fake_stream(**kw):
        seen.update(kw)
        yield "ok"

    agent.llm_instance.get_response_stream = fake_stream

    "".join(agent.start("x", stream=True))

    assert "chat_history" in seen, "the fake transport was never called"
    history = seen["chat_history"]
    assert len(history) <= SEEDED * 0.7, (
        f"streamed custom-LLM request carried {len(history)} history messages for "
        f"{SEEDED} seeded; context compaction did not run on the streaming path"
    )
    # The turn just appended must survive compaction.
    assert history[-1] == {"role": "user", "content": "x"}
