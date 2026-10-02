"""Concurrent Session closes must merge different agent histories under lock."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from praisonaiagents.session.api import AGENT_HISTORY_KEY, Session
from praisonaiagents.session.store import DefaultSessionStore


@pytest.mark.parametrize("existing", [{}, {"peer:Assistant": [
    {"role": "user", "content": "peer"},
]}])
def test_two_closes_preserve_both_agent_histories(tmp_path, monkeypatch, existing):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    directory = str(tmp_path / "sessions")
    first = DefaultSessionStore(session_dir=directory)
    second = DefaultSessionStore(session_dir=directory)
    first.update_session_metadata("parent", **{AGENT_HISTORY_KEY: existing})
    a, b = Session(session_id="parent"), Session(session_id="parent")
    monkeypatch.setattr(a, "_get_session_store", lambda: first)
    monkeypatch.setattr(b, "_get_session_store", lambda: second)
    ah = [{"role": "user", "content": "a"}]
    bh = [{"role": "user", "content": "b"}]
    a._agents["a:Assistant"] = {"agent": None, "chat_history": ah}
    b._agents["b:Assistant"] = {"agent": None, "chat_history": bh}
    ready, completed = Event(), Event()
    original = first._modify_session_locked

    def pause_before_lock(*args, **kwargs):
        ready.set()
        assert completed.wait(10), "second writer did not complete"
        return original(*args, **kwargs)

    monkeypatch.setattr(first, "_modify_session_locked", pause_before_lock)

    def close_second():
        assert ready.wait(10), "first writer did not reach write boundary"
        try:
            b.close()
        finally:
            completed.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        fa, fb = pool.submit(a.close), pool.submit(close_second)
        fa.result(timeout=15)
        fb.result(timeout=15)
    fresh = DefaultSessionStore(session_dir=directory)
    assert fresh.get_session("parent").metadata[AGENT_HISTORY_KEY] == {
        **existing, "a:Assistant": ah, "b:Assistant": bh,
    }


def test_metadata_map_defaults_do_not_overwrite_current_entries(tmp_path):
    store = DefaultSessionStore(session_dir=str(tmp_path))
    store.update_session_metadata("parent", marker="keep", **{AGENT_HISTORY_KEY: {
        "current": [], "peer": ["present"],
    }})
    assert store.merge_session_metadata_map(
        "parent", AGENT_HISTORY_KEY, {"new": ["new"]},
        defaults={"current": ["legacy"], "legacy-only": ["old"]},
    )
    data = DefaultSessionStore(session_dir=str(tmp_path)).get_session("parent")
    assert data.metadata[AGENT_HISTORY_KEY] == {
        "current": [], "peer": ["present"], "new": ["new"],
        "legacy-only": ["old"],
    }
    assert data.metadata["marker"] == "keep"


@pytest.mark.parametrize("failure", ["read", "write"])
def test_metadata_map_failure_preserves_disk(tmp_path, monkeypatch, failure):
    import praisonaiagents.session.store as store_module

    store = DefaultSessionStore(session_dir=str(tmp_path))
    store.update_session_metadata("parent", **{AGENT_HISTORY_KEY: {"peer": ["old"]}})
    path = Path(store._get_session_path("parent"))
    before = path.read_bytes()

    def fail(*args, **kwargs):
        raise OSError("injected I/O failure")

    if failure == "read":
        monkeypatch.setattr(store, "_load_session_from_disk", fail)
    else:
        monkeypatch.setattr(store_module.os, "replace", fail)
    assert not store.merge_session_metadata_map("parent", AGENT_HISTORY_KEY, {"new": []})
    assert path.read_bytes() == before
