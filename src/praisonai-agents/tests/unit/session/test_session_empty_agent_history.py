"""An explicitly empty agent transcript must override older saved history."""

from types import SimpleNamespace

import pytest

from praisonaiagents.session.api import AGENT_HISTORY_KEY, Session
from praisonaiagents.session.store import DefaultSessionStore


OLD = [{"role": "user", "content": "old conversation"}]
PEER = [{"role": "user", "content": "other agent"}]


@pytest.fixture
def setup(tmp_path, monkeypatch):
    import praisonaiagents.session.store as store_module

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    directory = str(tmp_path / "sessions")
    store = DefaultSessionStore(session_dir=directory)
    monkeypatch.setattr(store_module, "_default_store", store)
    return Session(session_id="parent"), store, directory, store_module


def test_close_persists_cleared_history_without_erasing_peer(setup, monkeypatch):
    session, store, directory, store_module = setup
    store.update_session_metadata("parent", **{AGENT_HISTORY_KEY: {
        "helper:Assistant": OLD, "peer:Assistant": PEER,
    }})
    session._agents["helper:Assistant"] = {
        "agent": SimpleNamespace(chat_history=[]), "chat_history": OLD,
    }
    session.close()
    fresh = DefaultSessionStore(session_dir=directory)
    monkeypatch.setattr(store_module, "_default_store", fresh)
    assert fresh.get_session("parent").metadata[AGENT_HISTORY_KEY] == {
        "helper:Assistant": [], "peer:Assistant": PEER,
    }


@pytest.mark.parametrize("legacy", [False, True], ids=["memory", "tagged-legacy"])
def test_empty_current_history_prevents_fallback_resurrection(setup, legacy):
    session, store, _, _ = setup
    store.update_session_metadata("parent", **{AGENT_HISTORY_KEY: {
        "helper:Assistant": [],
    }})
    if legacy:
        store.set_chat_history("parent_helper:Assistant", OLD)
        store.update_session_metadata(
            "parent_helper:Assistant", parent_session_id="parent",
            agent_key="helper:Assistant",
        )
    session._memory = SimpleNamespace(search_short_term=lambda **kwargs: [{
        "metadata": {"type": "agent_chat_history", "session_id": "parent",
                     "agent_key": "helper:Assistant", "chat_history": OLD},
    }])
    assert session._restore_agent_chat_history("helper:Assistant") == []
    session._restore_agent_chat_histories()
    assert session._agents["helper:Assistant"]["chat_history"] == []


@pytest.mark.parametrize("replacement", [[], [{"role": "user", "content": "new"}]])
def test_verified_replacement_succeeds_on_first_write(setup, monkeypatch, replacement):
    session, store, _, _ = setup
    store.update_session_metadata("parent", **{AGENT_HISTORY_KEY: {
        "helper:Assistant": OLD, "peer:Assistant": PEER,
    }})
    original = store.merge_session_metadata_map
    writes = []

    def merge(*args, **kwargs):
        writes.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "merge_session_metadata_map", merge)
    assert session._store_agent_history(store, "helper:Assistant", replacement)
    assert len(writes) == 1
    assert store.get_session("parent").metadata[AGENT_HISTORY_KEY] == {
        "helper:Assistant": replacement, "peer:Assistant": PEER,
    }
