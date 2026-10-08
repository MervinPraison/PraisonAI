"""Explicit reset recovers corrupt stores without weakening ordinary writes."""

import json
from pathlib import Path

import pytest

from praisonaiagents.memory.learn.stores import PersonaStore
from praisonaiagents.storage import base
from praisonaiagents.storage.base import BaseJSONStore


@pytest.fixture(params=["base", "learn", "training"])
def corrupt_store(request, tmp_path, monkeypatch):
    path = tmp_path / "session.json"
    path.write_bytes(b"\xff")
    if request.param == "base":
        store = BaseJSONStore(path)
        underlying = store
        expected = {}
    elif request.param == "learn":
        store = PersonaStore(store_path=str(path))
        underlying = store._store
        expected = {}
    else:
        monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[4] / "praisonai-train"))
        from praisonai_train.train.agents.storage import TrainingStorage

        store = TrainingStorage("session", storage_dir=tmp_path)
        underlying = store._store
        expected = {"session_id": "session", "scenarios": [], "iterations": [], "report": None}
    return store, underlying, path, expected


def test_explicit_clear_recovers_corrupt_store(corrupt_store):
    store, underlying, path, expected = corrupt_store
    store.clear()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert all(saved[key] == value for key, value in expected.items())
    if not expected:
        assert saved == {}
    underlying.save({"recovered": True})
    assert json.loads(path.read_text(encoding="utf-8")) == {"recovered": True}


def test_failed_explicit_clear_keeps_corrupt_source_guard(corrupt_store, monkeypatch):
    store, underlying, path, _ = corrupt_store
    replace = base.os.replace

    def fail_replace(*args):
        raise OSError("replacement failed")

    monkeypatch.setattr(base.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replacement failed"):
        store.clear()
    assert path.read_bytes() == b"\xff"
    with pytest.raises(OSError, match="unreadable"):
        underlying.save({"recovered": True})
    assert path.read_bytes() == b"\xff"
    monkeypatch.setattr(base.os, "replace", replace)
    store.clear()
    assert not underlying._read_failed
