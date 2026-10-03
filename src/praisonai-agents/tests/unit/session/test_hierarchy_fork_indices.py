"""Public fork boundaries must identify an actual message before writing."""

import json

import pytest

from praisonaiagents.session.hierarchy import HierarchicalSessionStore


def make_parent(tmp_path, count):
    store = HierarchicalSessionStore(session_dir=str(tmp_path), max_messages=100)
    store.create_session(session_id="parent", title="Parent")
    for index in range(count):
        assert store.add_message("parent", "user", f"message {index}")
    return store


@pytest.mark.parametrize(
    "count,index", [(3, -1), (3, -2), (3, -5), (3, 3), (3, 99), (0, 0), (0, -1)]
)
def test_invalid_fork_index_does_not_write(tmp_path, count, index):
    store = make_parent(tmp_path, count)
    parent_path = tmp_path / "parent.json"
    before = parent_path.read_bytes()

    with pytest.raises(ValueError, match="Invalid message index"):
        store.fork_session("parent", from_message_index=index)

    assert parent_path.read_bytes() == before
    assert sorted(path.name for path in tmp_path.glob("*.json")) == ["parent.json"]
    assert store.get_children("parent") == []


@pytest.mark.parametrize("count,index", [(3, None), (3, 0), (3, 2), (0, None)])
def test_valid_fork_index_is_inclusive_and_durable(tmp_path, count, index):
    store = make_parent(tmp_path, count)
    fork_id = store.fork_session("parent", from_message_index=index)

    fork = json.loads((tmp_path / f"{fork_id}.json").read_text(encoding="utf-8"))
    parent = json.loads((tmp_path / "parent.json").read_text(encoding="utf-8"))
    expected_count = count if index is None else index + 1
    assert [message["content"] for message in fork["messages"]] == [
        f"message {number}" for number in range(expected_count)
    ]
    assert fork["forked_from_message_id"] == (None if index is None else str(index))
    assert fork["parent_id"] == "parent"
    assert parent["children_ids"] == [fork_id]
