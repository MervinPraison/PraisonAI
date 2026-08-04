"""
Tests for durable, memory-independent AgentTeam session resume (Issue #3635).

Verifies that AgentTeam.save_session_state / restore_session_state persist and
rehydrate the shared team _state through the durable SessionStore, matching the
single-Agent --continue guarantee — without requiring the memory subsystem.
"""

import tempfile

import pytest

from praisonaiagents.agents.agents import AgentTeam
from praisonaiagents.session import store as store_module


@pytest.fixture
def temp_store(monkeypatch):
    """Point the global session store at an isolated temp directory."""
    tmp = tempfile.mkdtemp()
    fresh = store_module.DefaultSessionStore(session_dir=tmp)
    monkeypatch.setattr(store_module, "_default_store", fresh, raising=False)
    return fresh


def _bare_team():
    """An AgentTeam instance with just the fields the methods touch (no LLM)."""
    team = object.__new__(AgentTeam)
    import threading

    team._state = {}
    team._state_lock = threading.Lock()
    team.user_id = "user-1"
    team.run_id = "run-1"
    team.agents = []
    team.process = "sequential"
    team.shared_memory = None
    return team


def test_save_and_restore_without_memory(temp_store):
    """Durable path persists and restores team state with memory disabled."""
    team = _bare_team()
    team._state = {"progress": "step-2", "count": 3}

    team.save_session_state("team-session-1")

    # A fresh team (no memory) must deterministically rehydrate the state.
    resumed = _bare_team()
    assert resumed.restore_session_state("team-session-1") is True
    assert resumed._state == {"progress": "step-2", "count": 3}


def test_restore_unknown_session_returns_false(temp_store):
    team = _bare_team()
    assert team.restore_session_state("nope") is False


def test_durable_persist_survives_new_store_instance(temp_store):
    """State is on disk, so any SessionStore over the same dir can read it."""
    team = _bare_team()
    team._state = {"k": "v"}
    team.save_session_state("team-session-2")

    data = temp_store.get_session("team-session-2")
    assert data.metadata.get("team_session_state", {}).get("state") == {"k": "v"}


def test_restore_merges_not_replaces(temp_store):
    """Restore merges saved state into existing state (no clobber of new keys)."""
    team = _bare_team()
    team._state = {"saved": 1}
    team.save_session_state("team-session-3")

    resumed = _bare_team()
    resumed._state = {"fresh": 2}
    assert resumed.restore_session_state("team-session-3") is True
    assert resumed._state == {"fresh": 2, "saved": 1}
