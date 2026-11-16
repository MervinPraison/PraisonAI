"""G-11: memory and session save failures must be visible, not debug-only.

A failed memory write, session auto-save or index refresh was logged at
DEBUG, so with default logging the data was lost silently. These now log at
WARNING (naming the agent or session) and still never raise into the turn.
"""

import logging
from types import SimpleNamespace

import pytest

from praisonaiagents import Agent


def _agent(monkeypatch, tmp_path, **kwargs):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    return Agent(name="saver", instructions="hi", llm="gpt-4o-mini", output="silent", **kwargs)


def _boom(*args, **kwargs):
    raise OSError("disk full")


@pytest.mark.parametrize("tier", ["long", "short"])
def test_memory_turn_write_failure_is_a_warning(monkeypatch, tmp_path, caplog, tier):
    agent = _agent(monkeypatch, tmp_path)
    ok = lambda *a, **k: None
    agent._memory_instance = SimpleNamespace(
        store_long_term=_boom if tier == "long" else ok,
        store_short_term=_boom if tier == "short" else ok,
    )
    with caplog.at_level(logging.WARNING):
        agent._persist_memory_turn("q", "a")  # must not raise
    hits = [r for r in caplog.records if r.levelno == logging.WARNING and "memory turn persistence failed" in r.getMessage()]
    assert len(hits) == 1
    assert "saver" in hits[0].getMessage() and "disk full" in hits[0].getMessage()


def test_auto_save_failure_is_a_warning(monkeypatch, tmp_path, caplog):
    agent = _agent(monkeypatch, tmp_path)
    agent.auto_save = "sess-1"
    agent._session_store = None
    agent._memory_instance = SimpleNamespace(save_session=_boom)
    agent.chat_history.append({"role": "user", "content": "hi"})
    with caplog.at_level(logging.WARNING):
        agent._auto_save_session()  # must not raise
    hits = [r for r in caplog.records if r.levelno == logging.WARNING and "Auto-saving session" in r.getMessage()]
    assert len(hits) == 1
    assert "sess-1" in hits[0].getMessage() and "saver" in hits[0].getMessage()


def test_sqlite_index_refresh_failure_is_a_warning(tmp_path, caplog):
    from praisonaiagents.session.sqlite_store import SqliteSessionStore
    store = SqliteSessionStore(session_dir=str(tmp_path), db_path=":memory:")
    conn = store._connect()
    conn.execute("DROP TABLE session_meta")  # a real database write now fails
    with caplog.at_level(logging.WARNING):
        assert store.add_message("s1", "user", "hello") is True  # the JSON write still succeeds
    assert any(r.levelno == logging.WARNING and "Session index update failed for s1" in r.getMessage()
               for r in caplog.records)
