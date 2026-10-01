"""Sequential operations sharing a learning file must preserve peer writes."""

import pytest

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
