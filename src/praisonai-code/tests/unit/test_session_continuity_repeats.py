"""Regression tests for `run --continue` history restoration (Issue #4243).

`apply_cli_session_continuity` restored history using a content-based filter, so
repeated turns (the common case being a bare "yes" confirmation) were silently
dropped and the model resumed onto a conversation that never happened. History
must be restored by position: two identical turns are two turns.
"""

import pytest


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Isolated project dir + sessions home under the test sandbox."""
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


class _FakeAgent:
    def __init__(self):
        self.chat_history = []
        self.name = "tester"
        self.llm = "gpt-4o-mini"


def _store(session_id, contents):
    from praisonai_code.cli.state.project_sessions import get_project_session_store

    store = get_project_session_store()
    for i, content in enumerate(contents):
        role = "user" if i % 2 == 0 else "assistant"
        store.add_message(session_id, role, content)
    return store


def test_repeated_confirmations_survive_a_continue(project):
    """'yes' three times is three turns; collapsing them corrupts the history."""
    from praisonai_code.cli.state.project_sessions import apply_cli_session_continuity

    _store(
        "sess-yes",
        ["run the tests", "ok", "yes", "done 1", "yes", "done 2", "yes", "done 3"],
    )
    agent = _FakeAgent()
    apply_cli_session_continuity(agent, "sess-yes")

    assert len(agent.chat_history) == 8
    assert [m["content"] for m in agent.chat_history].count("yes") == 3


def test_auto_save_index_matches_full_restored_length(project):
    """The auto-save offset must equal the full restored length, not a deduped one."""
    from praisonai_code.cli.state.project_sessions import apply_cli_session_continuity

    _store("sess-idx", ["a", "b", "a", "b"])
    agent = _FakeAgent()
    apply_cli_session_continuity(agent, "sess-idx")

    assert agent._auto_save_last_index == len(agent.chat_history) == 4


def test_no_duplicate_when_history_already_present(project):
    """If chat_history already holds the stored history verbatim, do not re-add it."""
    from praisonai_code.cli.state.project_sessions import apply_cli_session_continuity

    _store("sess-dup", ["x", "y"])
    agent = _FakeAgent()
    agent.chat_history = [
        {"role": "user", "content": "x"},
        {"role": "assistant", "content": "y"},
    ]
    apply_cli_session_continuity(agent, "sess-dup")

    assert len(agent.chat_history) == 2
