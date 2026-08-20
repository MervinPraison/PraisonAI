"""A sub-agent transcript must never overwrite an unrelated user session.

``Session.Agent(name, role)`` used to persist the agent's transcript as a
*separate top-level session* named ``f"{session_id}_{name}:{role}"``. The store
rewrites every character outside ``[A-Za-z0-9-_]`` to ``_``, so
``Session("chat")`` + agent ``support:agent`` resolved to
``chat_support_agent.json`` — the same file as a real user session named
``chat_support_agent`` — and ``set_chat_history`` replaces, so an ordinary
``Session.close()`` destroyed that user's transcript.
"""

import pytest

from praisonaiagents.session.store import DefaultSessionStore

# Spelled out rather than imported from session.api so this file also runs
# (and fails) against the unpatched module.
AGENT_HISTORY_KEY = "agent_histories"
LEGACY_AGENT_KEYS_ENV = "PRAISONAI_SESSION_LEGACY_AGENT_KEYS"

REAL = [{"role": "user", "content": "MY REAL CONVERSATION"}]
SUB = [{"role": "user", "content": "unrelated sub-agent history"}]


@pytest.fixture
def store(tmp_path, monkeypatch):
    """An isolated default session store."""
    import praisonaiagents.session.store as store_module

    fresh = DefaultSessionStore(session_dir=str(tmp_path / "sessions"))
    monkeypatch.setattr(store_module, "_default_store", fresh, raising=False)
    return fresh


@pytest.fixture
def session(tmp_path, monkeypatch):
    """A ``Session("chat")`` that touches no real user data directories."""
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    from praisonaiagents.session.api import Session

    return Session(session_id="chat")


def test_close_does_not_overwrite_colliding_user_session(store, session):
    """Saving a sub-agent must not touch a same-named unrelated session."""
    store.set_chat_history("chat_support_agent", REAL)

    session._agents["support:agent"] = {"agent": None, "chat_history": SUB}
    session._save_agent_chat_histories()

    assert store.get_chat_history("chat_support_agent") == REAL


def test_colliding_user_session_is_not_read_as_agent_history(store, session):
    """Nor may that unrelated session leak *into* the sub-agent."""
    store.set_chat_history("chat_support_agent", REAL)

    assert session._restore_agent_chat_history("support:agent") == []


def test_agent_history_round_trips_via_parent_record(store, session):
    """The transcript is stored on, and restored from, the parent record."""
    session._agents["support:agent"] = {"agent": None, "chat_history": SUB}
    session._save_agent_chat_histories()

    assert store.get_session("chat").metadata[AGENT_HISTORY_KEY] == {
        "support:agent": SUB
    }
    assert session._restore_agent_chat_history("support:agent") == SUB


def test_tagged_legacy_child_is_migrated_into_the_parent(store, session):
    """Tagged legacy children are readable and carried forward on save."""
    store.set_chat_history("chat_support:agent", REAL)
    store.update_session_metadata(
        "chat_support:agent", parent_session_id="chat", agent_key="support:agent"
    )

    assert session._restore_agent_chat_history("support:agent") == REAL

    session._agents["other:agent"] = {"agent": None, "chat_history": SUB}
    session._save_agent_chat_histories()

    assert store.get_session("chat").metadata[AGENT_HISTORY_KEY] == {
        "support:agent": REAL,
        "other:agent": SUB,
    }


def test_untagged_legacy_child_restores_only_when_opted_in(
    store, session, monkeypatch
):
    """Pre-tag sub-agent history stays reachable behind an explicit opt-in."""
    store.set_chat_history("chat_support:agent", REAL)

    assert session._restore_agent_chat_history("support:agent") == []

    monkeypatch.setenv(LEGACY_AGENT_KEYS_ENV, "1")
    assert session._restore_agent_chat_history("support:agent") == REAL
