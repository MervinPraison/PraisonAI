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


def test_tagged_legacy_child_restored_even_when_partially_migrated(store, session):
    """A tagged legacy agent must resume even if the parent already holds
    a *different* agent in the current format (partial migration)."""
    # Agent A already migrated into the parent's own record.
    store.update_session_metadata("chat", **{AGENT_HISTORY_KEY: {"a:agent": SUB}})
    # Agent B still lives only in a tagged legacy record.
    store.set_chat_history("chat_support:agent", REAL)
    store.update_session_metadata(
        "chat_support:agent", parent_session_id="chat", agent_key="support:agent"
    )

    assert session._restore_agent_chat_history("support:agent") == REAL

    session._restore_agent_chat_histories()
    assert session._agents["a:agent"]["chat_history"] == SUB
    assert session._agents["support:agent"]["chat_history"] == REAL


def test_tagged_legacy_child_migrated_even_when_not_recently_updated(store, session):
    """A legacy per-agent record is older than everything written after the
    upgrade, so the migration must not inherit ``list_sessions()``'s 50-record
    window (regression from #4126)."""
    store.set_chat_history("chat_support:agent", REAL)
    store.update_session_metadata(
        "chat_support:agent", parent_session_id="chat", agent_key="support:agent"
    )
    # Bury the legacy record well outside the default 50-session window with
    # strictly newer sessions.
    for i in range(60):
        store.set_chat_history(f"other-{i:04d}", SUB)

    assert session._restore_agent_chat_history("support:agent") == REAL


def test_concurrent_save_preserves_other_agents(store, session):
    """A second writer under the same parent must not drop the first's entry."""
    session._agents["a:agent"] = {"agent": None, "chat_history": REAL}
    session._save_agent_chat_histories()

    from praisonaiagents.session.api import Session

    other = Session(session_id="chat")
    other._agents["b:agent"] = {"agent": None, "chat_history": SUB}
    other._save_agent_chat_histories()

    stored = store.get_session("chat").metadata[AGENT_HISTORY_KEY]
    assert stored == {"a:agent": REAL, "b:agent": SUB}
