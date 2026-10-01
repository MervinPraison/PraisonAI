"""Hierarchy writes must honor the inherited retention policy before slicing."""

import json

import pytest

from praisonaiagents.session.hierarchy import HierarchicalSessionStore
from praisonaiagents.session.store import DefaultSessionStore, SessionData, SessionMessage


@pytest.mark.parametrize("operation", ["add", "fork", "import"])
@pytest.mark.parametrize(
    "retention,window,active,archived",
    [
        ("keep_all", 2, ["0", "1", "2", "3", "4"], []),
        ("compact", 2, ["3", "4"], ["0", "1", "2"]),
        ("truncate", 4, ["1", "2", "3", "4"], []),
        (None, None, ["3", "4"], []),
    ],
)
def test_retention_survives_public_hierarchy_writes(
    tmp_path, operation, retention, window, active, archived
):
    store = HierarchicalSessionStore(
        session_dir=str(tmp_path), max_messages=2,
        retention=retention, active_window=window,
    )
    messages = [SessionMessage("user", str(index), timestamp=index) for index in range(5)]
    if operation == "add":
        result_id = store.create_session(session_id="parent")
        for message in messages:
            assert store.add_message(result_id, message.role, message.content)
    elif operation == "fork":
        source = DefaultSessionStore(session_dir=str(tmp_path), retention="keep_all")
        for message in messages:
            assert source.add_message("parent", message.role, message.content)
        result_id = store.fork_session("parent")
    else:
        result_id = store.import_session(
            SessionData(session_id="source", messages=messages).to_dict(),
            new_session_id="imported",
        )

    result = json.loads((tmp_path / f"{result_id}.json").read_text(encoding="utf-8"))
    raw_active = [message for message in result["messages"] if not message["metadata"].get("compaction")]
    assert [message["content"] for message in raw_active] == active
    assert [message["content"] for message in result["archived_messages"]] == archived
    if retention == "compact":
        summary = result["messages"][0]
        assert summary["role"] == "system"
        assert summary["metadata"]["compaction"] is True
        assert summary["metadata"]["compacted_count"] == 3
    reopened = HierarchicalSessionStore(session_dir=str(tmp_path))
    fresh = reopened.get_extended_session(result_id, force_reload=True)
    assert [message.content for message in fresh.archived_messages] == archived


def test_truncate_does_not_persist_orphaned_tool_result(tmp_path):
    store = HierarchicalSessionStore(
        session_dir=str(tmp_path), max_messages=2, retention="truncate"
    )
    calls = [{"id": "call1", "type": "function", "function": {"name": "read", "arguments": "{}"}}]
    assert store.add_message("parent", "assistant", "", tool_calls=calls)
    assert store.add_message("parent", "tool", "result", tool_call_id="call1")
    assert store.add_message("parent", "user", "next")

    result = json.loads((tmp_path / "parent.json").read_text(encoding="utf-8"))
    assert [message["role"] for message in result["messages"]] == ["user"]
    assert result["messages"][0]["content"] == "next"
