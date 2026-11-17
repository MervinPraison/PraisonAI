"""X-12: ``Session.save_state()`` works on a fresh session and needs no model.

It wrote the state through short-term memory. With chromadb installed that
meant an embeddings API call (network, cost) to store a small dict; when that
failed, the legacy fallback hit ``no such table: short_mem`` and raised, and
``restore_state()`` returned ``{}``. State now lives on the session record,
like sub-agent histories; states saved by older versions still restore.
"""

import pytest

from praisonaiagents import Session


@pytest.fixture
def clean(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home" / ".praisonai"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    monkeypatch.chdir(tmp_path)
    from praisonaiagents.session import store as store_mod
    monkeypatch.setattr(store_mod, "_default_store", None, raising=False)
    return tmp_path


def test_save_and_restore_on_a_fresh_session(clean, monkeypatch):
    from praisonaiagents.memory.memory import Memory

    def no_memory(*args, **kwargs):
        raise AssertionError("save_state must not go through memory (embeddings)")

    monkeypatch.setattr(Memory, "store_short_term", no_memory)
    session = Session(session_id="s1", user_id="u1")
    session.save_state({"k": "v", "n": 3})
    assert Session(session_id="s1", user_id="u1").restore_state() == {"k": "v", "n": 3}


def test_last_save_wins(clean):
    session = Session(session_id="s2", user_id="u1")
    session.save_state({"step": 1})
    session.save_state({"step": 2})
    assert session.restore_state() == {"step": 2}


def test_state_saved_by_an_older_version_still_restores(clean, monkeypatch):
    # Older versions stored state as a short-term memory record.
    session = Session(session_id="s3", user_id="u1")

    class _OldMemory:
        def search_short_term(self, query, limit=10, **kwargs):
            if query == "Session state:":
                return [{"metadata": {"type": "session_state", "session_id": "s3",
                                      "user_id": "u1", "k": "old"}}]
            return []

    session._memory = _OldMemory()
    assert session.restore_state() == {"k": "old"}
