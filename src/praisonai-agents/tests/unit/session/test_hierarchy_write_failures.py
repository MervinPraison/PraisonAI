"""Hierarchy creation reports failed durable writes instead of returning IDs."""

import os
from pathlib import Path

import pytest

from praisonaiagents.session.hierarchy import HierarchicalSessionStore
from praisonaiagents.session.store import FileLock


@pytest.fixture
def store(tmp_path):
    result = HierarchicalSessionStore(session_dir=str(tmp_path))
    result.create_session("parent", title="Original")
    assert result.add_message("parent", "user", "original turn")
    return result


def invoke(store, operation):
    if operation == "create":
        return store.create_session("new", title="New")
    if operation == "fork":
        return store.fork_session("parent")
    if operation == "snapshot":
        return store.create_snapshot("parent", label="Snapshot")
    return store.import_session({"session_id": "source", "messages": []}, new_session_id="new")


@pytest.mark.parametrize("operation", ["create", "fork", "snapshot", "import"])
def test_failed_replace_raises_instead_of_returning_id(store, monkeypatch, operation):
    def fail(*args):
        raise OSError("injected replace failure")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        invoke(store, operation)
    store.invalidate_cache()
    parent = store.get_extended_session("parent", force_reload=True)
    assert parent.children_ids == []
    assert parent.snapshots == []
    assert [message.content for message in parent.messages] == ["original turn"]
    assert not store.session_exists("new")


def test_failed_child_save_does_not_register_missing_child(store, monkeypatch):
    original = os.replace

    def fail_child(source, destination):
        if os.path.basename(destination) == "child.json":
            raise OSError("injected child replace failure")
        return original(source, destination)

    monkeypatch.setattr(os, "replace", fail_child)
    with pytest.raises(OSError):
        store.create_session("child", parent_id="parent")
    assert store.get_children("parent") == []
    assert not store.session_exists("child")


@pytest.mark.parametrize("operation", ["create", "fork"])
def test_failed_parent_registration_reports_retained_child(store, monkeypatch, operation):
    original = os.replace

    def fail_parent(source, destination):
        if os.path.basename(destination) == "parent.json":
            raise OSError("injected parent replace failure")
        return original(source, destination)

    monkeypatch.setattr(os, "replace", fail_parent)
    with pytest.raises(OSError, match="parent"):
        if operation == "create":
            store.create_session("child", parent_id="parent")
        else:
            store.fork_session("parent")
    store.invalidate_cache()
    assert store.get_children("parent") == []
    children = [row["session_id"] for row in store.list_sessions() if row["session_id"] != "parent"]
    assert len(children) == 1
    assert store.get_parent(children[0]) == "parent"


@pytest.mark.parametrize("operation", ["create", "fork", "snapshot", "import"])
def test_successful_operation_returns_persisted_id(store, operation):
    identifier = invoke(store, operation)
    assert isinstance(identifier, str) and identifier
    if operation == "snapshot":
        assert identifier in [snapshot.id for snapshot in store.get_snapshots("parent")]
    else:
        assert store.session_exists(identifier)


@pytest.mark.parametrize("session_id", ["new", "parent"])
def test_self_parent_is_rejected_before_any_session_write(store, session_id):
    parent_path = Path(store.session_dir) / "parent.json"
    before = parent_path.read_bytes()
    with pytest.raises(ValueError, match="parent"):
        store.create_session(session_id, parent_id=session_id)
    assert parent_path.read_bytes() == before
    assert not store.session_exists("new")
    assert store.get_session_tree("parent")["children"] == []


@pytest.mark.parametrize("operation", ["create", "fork"])
def test_parent_lock_failure_reports_durable_child(store, monkeypatch, operation):
    """A lock-acquisition exception identifies the already saved child."""
    import praisonaiagents.session.hierarchy as hierarchy

    child_path = Path(store.session_dir) / "child.json"
    acquire = FileLock.acquire

    def fail_registration(lock):
        if Path(lock.filepath).name == "parent.json" and child_path.exists():
            return False
        return acquire(lock)

    monkeypatch.setattr(FileLock, "acquire", fail_registration)
    monkeypatch.setattr(hierarchy.uuid, "uuid4", lambda: "child")
    with pytest.raises(OSError) as caught:
        if operation == "create":
            store.create_session("child", parent_id="parent")
        else:
            store.fork_session("parent")
    assert "child" in str(caught.value)
    assert "parent" in str(caught.value)
    assert "was saved" in str(caught.value)
    assert isinstance(caught.value.__cause__, OSError)
    assert child_path.exists()
    monkeypatch.setattr(FileLock, "acquire", acquire)
    reopened = HierarchicalSessionStore(session_dir=store.session_dir)
    assert reopened.get_parent("child") == "parent"
    assert reopened.get_children("parent") == []


@pytest.mark.parametrize("operation", ["create", "fork"])
def test_parent_release_error_preserves_committed_registration(store, monkeypatch, operation):
    """A post-write lock error must not claim the parent update failed."""
    import praisonaiagents.session.hierarchy as hierarchy

    child_path = Path(store.session_dir) / "child.json"
    release = FileLock.release

    def fail_after_release(lock):
        """Release the real lock before reporting a parent cleanup error."""
        release(lock)
        if Path(lock.filepath).name == "parent.json" and child_path.exists():
            raise OSError("injected parent lock cleanup failure")

    monkeypatch.setattr(FileLock, "release", fail_after_release)
    monkeypatch.setattr(hierarchy.uuid, "uuid4", lambda: "child")
    with pytest.raises(OSError) as caught:
        if operation == "create":
            store.create_session("child", parent_id="parent")
        else:
            store.fork_session("parent")
    message = str(caught.value)
    assert "child" in message and "parent" in message
    assert "may already be committed" in message
    assert "failed" not in message
    assert isinstance(caught.value.__cause__, OSError)
    monkeypatch.setattr(FileLock, "release", release)
    reopened = HierarchicalSessionStore(session_dir=store.session_dir)
    assert reopened.get_parent("child") == "parent"
    assert reopened.get_children("parent") == ["child"]
