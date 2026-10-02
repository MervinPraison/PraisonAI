"""Failed atomic file writes must not leave partial staging files."""

import pytest

from praisonaiagents.storage.backends import FileBackend


@pytest.mark.parametrize("pretty", [True, False])
@pytest.mark.parametrize("failure", ["circular", "invalid_key", "replace"])
def test_failed_save_preserves_destination_and_removes_staging(tmp_path, monkeypatch, pretty, failure):
    import praisonaiagents.storage.backends as module

    store = FileBackend(storage_dir=str(tmp_path), pretty=pretty)
    store.save("session", {"messages": ["keep"]})
    destination = tmp_path / "session.json"
    original = destination.read_bytes()
    if failure == "circular":
        data = {"messages": []}
        data["messages"].append(data)
        error = ValueError
    elif failure == "invalid_key":
        data = {"messages": ["partial"], (1, 2): "invalid"}
        error = TypeError
    else:
        data = {"messages": ["new"]}
        error = OSError

        def fail_replace(*args):
            raise OSError("replacement failed")

        monkeypatch.setattr(module.os, "replace", fail_replace)
    with pytest.raises(error):
        store.save("session", data)
    assert destination.read_bytes() == original
    assert store.load("session") == {"messages": ["keep"]}
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.parametrize("pretty", [True, False])
def test_successful_save_replaces_destination_without_staging(tmp_path, pretty):
    store = FileBackend(storage_dir=str(tmp_path), pretty=pretty)
    store.save("session", {"messages": ["old"]})
    store.save("session", {"messages": ["new"]})
    assert store.load("session") == {"messages": ["new"]}
    assert list(tmp_path.glob("*.tmp")) == []
