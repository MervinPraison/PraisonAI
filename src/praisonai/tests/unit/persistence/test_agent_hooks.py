"""Tests for the orchestrator-based persistence facade (agent_hooks).

Exercises ``wrap_agent_with_persistence``, ``PersistentAgent`` and
``create_persistent_session`` end-to-end against a real SQLite store so the
documented alternative entry point cannot silently drift from
``PersistenceOrchestrator``.
"""

import asyncio

import pytest

from praisonai.persistence import (
    PersistenceOrchestrator,
    PersistentAgent,
    create_persistent_session,
    wrap_agent_with_persistence,
)
from praisonai.persistence.conversation.sqlite import SQLiteConversationStore


class _EchoAgent:
    """Minimal agent stand-in: no LLM, deterministic replies."""

    name = "echo"

    def __init__(self):
        self.chat_history = []

    def chat(self, prompt, *args, **kwargs):
        return f"echo: {prompt}"

    async def achat(self, prompt, *args, **kwargs):
        return f"echo: {prompt}"


@pytest.fixture
def orchestrator(tmp_path):
    store = SQLiteConversationStore(path=str(tmp_path / "conv.db"))
    orch = PersistenceOrchestrator(conversation_store=store)
    yield orch
    store.close()


def _pairs(messages):
    return [(m.role, m.content) for m in messages]


def test_wrap_agent_with_persistence_persists_and_resumes(orchestrator):
    agent = wrap_agent_with_persistence(_EchoAgent(), orchestrator, session_id="s1")

    assert agent.chat("hi") == "echo: hi"
    assert _pairs(agent.get_messages()) == [("user", "hi"), ("assistant", "echo: hi")]
    assert agent.get_session().session_id == "s1"
    agent.end_session()

    resumed = wrap_agent_with_persistence(_EchoAgent(), orchestrator, session_id="s1")
    resumed.chat("again")
    assert resumed.chat_history[:2] == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "echo: hi"},
    ]
    assert len(resumed.get_messages()) == 4


def test_wrap_agent_with_persistence_async(orchestrator):
    agent = wrap_agent_with_persistence(_EchoAgent(), orchestrator, session_id="s2")

    assert asyncio.run(agent.achat("hi")) == "echo: hi"
    assert _pairs(orchestrator.get_messages("s2")) == [
        ("user", "hi"),
        ("assistant", "echo: hi"),
    ]


def test_persistent_agent_delegates_and_persists(orchestrator):
    base = _EchoAgent()
    agent = PersistentAgent(base, orchestrator, session_id="s3")

    assert agent.session_id == "s3"
    assert agent.name == "echo"  # attribute delegation
    assert agent.chat("hi") == "echo: hi"
    assert asyncio.run(agent.achat("yo")) == "echo: yo"
    assert _pairs(agent.get_messages()) == [
        ("user", "hi"),
        ("assistant", "echo: hi"),
        ("user", "yo"),
        ("assistant", "echo: yo"),
    ]
    agent.end_session()


def test_create_persistent_session_context_manager(orchestrator):
    with create_persistent_session(orchestrator, session_id="s4") as session:
        session.persist_message("user", "hi")
        session.persist_message("assistant", "hello")

    assert session.get_session().session_id == "s4"
    assert _pairs(session.get_messages()) == [("user", "hi"), ("assistant", "hello")]
