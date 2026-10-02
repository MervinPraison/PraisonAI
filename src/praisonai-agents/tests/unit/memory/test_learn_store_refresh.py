"""Sequential operations sharing a learning file must preserve peer writes."""

import pytest
import builtins
import json
from pathlib import Path

from praisonaiagents.memory.learn.stores import InsightStore


@pytest.mark.parametrize("operation", ["search", "list_all", "update", "delete"])
def test_stale_operations_preserve_peer_entry(tmp_path, operation):
    path = str(tmp_path / "insights.json")
    first = InsightStore(store_path=path)
    target = first.add("original target")
    second = InsightStore(store_path=path)
    survivor = second.add("peer survivor", {"source": "peer"})
    if operation == "search":
        results = first.search("target")
        assert [entry.id for entry in results] == [target.id]
        assert results[0].use_count == 1
    elif operation == "list_all":
        results = first.list_all()
        assert {entry.id for entry in results} == {target.id, survivor.id}
        assert all(entry.use_count == 1 for entry in results)
    elif operation == "update":
        assert first.update(target.id, "updated target").content == "updated target"
    else:
        assert first.delete(target.id)
    reopened = InsightStore(store_path=path)
    saved_survivor = reopened.get(survivor.id)
    assert saved_survivor is not None
    assert saved_survivor.content == "peer survivor"
    assert saved_survivor.metadata == {"source": "peer"}
    saved_target = reopened.get(target.id)
    assert (saved_target is None) == (operation == "delete")
    if operation == "update":
        assert saved_target.content == "updated target"


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_peer_added_target_is_available(tmp_path, operation):
    path = str(tmp_path / "insights.json")
    first = InsightStore(store_path=path)
    second = InsightStore(store_path=path)
    target = second.add("new target")
    if operation == "update":
        assert first.update(target.id, "updated").content == "updated"
        assert InsightStore(store_path=path).get(target.id).content == "updated"
    else:
        assert first.delete(target.id)
        assert InsightStore(store_path=path).get(target.id) is None


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_missing_target_control(tmp_path, operation):
    path = str(tmp_path / "insights.json")
    store = InsightStore(store_path=path)
    target = store.add("existing")
    store.reset_updated()
    if operation == "update":
        assert store.update("missing", "replacement") is None
    else:
        assert store.delete("missing") is False
    assert not store.was_updated
    assert InsightStore(store_path=path).get(target.id).content == "existing"


class UnavailableBackend:
    def __init__(self):
        self.data = None
        self.unavailable = False
        self.saves = 0

    def load(self, key):
        if self.unavailable:
            raise ConnectionError("backend unavailable")
        return self.data

    def save(self, key, data):
        self.saves += 1
        self.data = data


def test_search_finds_peer_addition_when_cache_has_no_match(tmp_path):
    path = str(tmp_path / "insights.json")
    first = InsightStore(store_path=path)
    first.add("unrelated")
    peer = InsightStore(store_path=path)
    target = peer.add("new matching record")
    results = first.search("matching")
    assert [entry.id for entry in results] == [target.id]
    assert results[0].use_count == 1


@pytest.mark.parametrize("operation", ["search", "list_all"])
@pytest.mark.parametrize("has_match", [False, True])
def test_backend_outage_reads_cache_without_writing(tmp_path, operation, has_match):
    backend = UnavailableBackend()
    store = InsightStore(store_path=str(tmp_path / "insights.json"), backend=backend)
    target = store.add("cached target") if has_match else None
    saves_before = backend.saves
    store.reset_updated()
    backend.unavailable = True
    results = store.search("target") if operation == "search" else store.list_all()
    assert [entry.id for entry in results] == ([target.id] if target else [])
    assert all(entry.use_count == 0 and entry.last_used is None for entry in results)
    assert backend.saves == saves_before
    assert not store.was_updated


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_backend_outage_mutations_fail_without_writing(tmp_path, operation):
    backend = UnavailableBackend()
    store = InsightStore(store_path=str(tmp_path / "insights.json"), backend=backend)
    target = store.add("cached target")
    saves_before = backend.saves
    backend.unavailable = True
    with pytest.raises(ConnectionError):
        if operation == "update":
            store.update(target.id, "replacement")
        else:
            store.delete(target.id)
    assert backend.saves == saves_before
    assert store.get(target.id).content == "cached target"


@pytest.mark.parametrize("operation", ["search", "list_all"])
@pytest.mark.parametrize("missing_field", ["id", "content"])
def test_malformed_record_is_not_treated_as_backend_outage(tmp_path, operation, missing_field):
    backend = UnavailableBackend()
    store = InsightStore(store_path=str(tmp_path / "insights.json"), backend=backend)
    target = store.add("cached target")
    malformed = target.to_dict()
    del malformed[missing_field]
    backend.data = {target.id: malformed}
    saves_before = backend.saves
    with pytest.raises(KeyError, match=missing_field):
        if operation == "search":
            store.search("target")
        else:
            store.list_all()
    assert backend.saves == saves_before


@pytest.mark.parametrize("operation", ["search", "list_all", "update", "delete"])
@pytest.mark.parametrize("failure", ["io", "json", "utf8"])
def test_file_refresh_failure_preserves_cache_and_source(tmp_path, monkeypatch, operation, failure):
    path = tmp_path / "insights.json"
    store = InsightStore(store_path=str(path))
    target = store.add("cached target")
    store.reset_updated()
    real_open = builtins.open
    if failure == "io":
        def denied(file, mode="r", *args, **kwargs):
            if Path(file) == path and mode == "r":
                raise PermissionError("injected read outage")
            return real_open(file, mode, *args, **kwargs)
        monkeypatch.setattr(builtins, "open", denied)
        expected_error = PermissionError
    else:
        path.write_bytes(b"{invalid" if failure == "json" else b"\xff")
        expected_error = json.JSONDecodeError if failure == "json" else UnicodeDecodeError
    before = path.read_bytes()
    if operation in ("search", "list_all"):
        results = store.search("target") if operation == "search" else store.list_all()
        assert [entry.id for entry in results] == [target.id]
        assert results[0].use_count == 0
        assert results[0].last_used is None
    else:
        with pytest.raises(expected_error):
            if operation == "update":
                store.update(target.id, "replacement")
            else:
                store.delete(target.id)
    assert store.get(target.id).content == "cached target"
    assert not store.was_updated
    assert path.read_bytes() == before


@pytest.mark.parametrize("operation", ["search", "list_all"])
def test_partial_deserialization_failure_preserves_all_cached_entries(tmp_path, operation):
    backend = UnavailableBackend()
    store = InsightStore(store_path=str(tmp_path / "insights.json"), backend=backend)
    target = store.add("cached target")
    backend.data = {target.id: target.to_dict(), "broken": {"id": "broken"}}
    with pytest.raises(KeyError, match="content"):
        if operation == "search":
            store.search("target")
        else:
            store.list_all()
    assert store.get(target.id) is target


def test_missing_runtime_file_initializes_fresh_store(tmp_path):
    path = tmp_path / "insights.json"
    store = InsightStore(store_path=str(path))
    original = store.add("original")
    path.unlink()
    assert store.list_all() == []
    assert store.get(original.id) is None
    replacement = store.add("replacement")
    assert InsightStore(store_path=str(path)).get(replacement.id).content == "replacement"


def test_invalid_json_initialization_keeps_existing_default_behavior(tmp_path):
    path = tmp_path / "insights.json"
    path.write_bytes(b"{invalid")
    store = InsightStore(store_path=str(path))
    assert store.get("missing") is None
    assert path.read_bytes() == b"{invalid"
