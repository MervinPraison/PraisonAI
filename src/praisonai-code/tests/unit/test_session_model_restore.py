"""Regression tests for restoring a resumed session's model (Issue #3685).

Conversation history was durably restored on ``--continue``/``--session`` but
the model the session was running was not: with no explicit ``--model``, resume
re-resolved the *current* default, so a change to the user's default between
runs silently switched the model mid-conversation. These tests assert the
recorded model is restored, and that an explicit model still wins.
"""

import pytest

from praisonaiagents.session.store import DefaultSessionStore


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Run inside an isolated project dir with an isolated sessions home."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / ".praison_home"))
    import praisonaiagents.paths as _paths

    sessions_dir = tmp_path / "sessions"

    def _fake_get_sessions_dir():
        sessions_dir.mkdir(parents=True, exist_ok=True)
        return sessions_dir

    monkeypatch.setattr(_paths, "get_sessions_dir", _fake_get_sessions_dir)
    monkeypatch.setattr(
        "praisonaiagents.session.store.get_sessions_dir", _fake_get_sessions_dir
    )
    return tmp_path


def test_get_session_model_reads_session_level_metadata(tmp_path):
    """Core accessor returns the session-level recorded model."""
    store = DefaultSessionStore(session_dir=str(tmp_path / "s"))
    store.add_message("sess", "user", "hello")
    store.update_session_metadata("sess", model="gpt-4o")
    assert store.get_session_model("sess") == "gpt-4o"


def test_get_session_model_falls_back_to_turn_metadata(tmp_path):
    """When no session-level model is set, the latest turn's model is used."""
    store = DefaultSessionStore(session_dir=str(tmp_path / "s"))
    store.add_message("sess", "user", "hello")
    store.add_message(
        "sess", "assistant", "hi", metadata={"model": "claude-3-5-sonnet"}
    )
    assert store.get_session_model("sess") == "claude-3-5-sonnet"


def test_get_session_model_latest_turn_wins(tmp_path):
    """With multiple recorded turns, the most recent model is returned."""
    store = DefaultSessionStore(session_dir=str(tmp_path / "s"))
    store.add_message("sess", "assistant", "one", metadata={"model": "gpt-4o"})
    store.add_message(
        "sess", "assistant", "two", metadata={"model": "claude-3-5-sonnet"}
    )
    assert store.get_session_model("sess") == "claude-3-5-sonnet"


def test_get_session_model_none_when_unrecorded(tmp_path):
    """No recorded model → None so the caller falls back to default resolution."""
    store = DefaultSessionStore(session_dir=str(tmp_path / "s"))
    store.add_message("sess", "user", "hello")
    assert store.get_session_model("sess") is None


def test_from_dict_restores_legacy_top_level_model():
    """Legacy sessions that stored ``model`` only at the top level still resolve.

    ``to_dict`` mirrors metadata keys to the top level; a historical/externally
    written file may carry ``model`` there but not under ``metadata``. ``from_dict``
    must fold it back so resume recovers the recorded model (Issue #3685).
    """
    from praisonaiagents.session.store import SessionData

    restored = SessionData.from_dict(
        {"session_id": "legacy", "messages": [], "model": "gpt-4o"}
    )
    assert restored.metadata.get("model") == "gpt-4o"


def test_from_dict_prefers_existing_metadata_over_top_level():
    """Existing ``metadata`` always wins over the mirrored top-level value."""
    from praisonaiagents.session.store import SessionData

    restored = SessionData.from_dict(
        {
            "session_id": "legacy",
            "messages": [],
            "model": "gpt-4o",
            "metadata": {"model": "claude-3-5-sonnet"},
        }
    )
    assert restored.metadata.get("model") == "claude-3-5-sonnet"


def test_find_session_model_resolves_recorded_model(project):
    """The wrapper helper resolves a recorded model from the project store."""
    from praisonai_code.cli.state.project_sessions import (
        find_session_model,
        get_project_session_store,
    )

    store = get_project_session_store()
    store.add_message("sess-model", "user", "hello")
    store.update_session_metadata("sess-model", model="gpt-4o-mini")

    assert find_session_model("sess-model") == "gpt-4o-mini"


def test_find_session_model_none_for_unknown_session(project):
    """An unknown / unrecorded session resolves to None (default fallback)."""
    from praisonai_code.cli.state.project_sessions import find_session_model

    assert find_session_model("does-not-exist") is None


def test_find_session_reasoning_effort_resolves_recorded(project):
    """The graded reasoning effort restores from the project store (Issue #4452)."""
    from praisonai_code.cli.state.project_sessions import (
        find_session_reasoning_effort,
        get_project_session_store,
    )

    store = get_project_session_store()
    store.add_message("sess-effort", "user", "hello")
    store.update_session_metadata("sess-effort", reasoning_effort="high")

    assert find_session_reasoning_effort("sess-effort") == "high"


def test_find_session_reasoning_effort_none_for_unknown(project):
    """An unrecorded effort resolves to None so the default is used."""
    from praisonai_code.cli.state.project_sessions import find_session_reasoning_effort

    assert find_session_reasoning_effort("does-not-exist") is None
