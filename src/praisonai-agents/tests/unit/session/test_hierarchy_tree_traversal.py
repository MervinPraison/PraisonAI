"""Tree reads handle deep valid histories and reject cyclic child paths."""

import json
import sys

import pytest

from praisonaiagents.session.hierarchy import ExtendedSessionData, HierarchicalSessionStore


def write_graph(tmp_path, graph):
    for session_id, children in graph.items():
        session = ExtendedSessionData(
            session_id=session_id, title=session_id, children_ids=children
        )
        (tmp_path / f"{session_id}.json").write_text(
            json.dumps(session.to_dict()), encoding="utf-8"
        )
    return HierarchicalSessionStore(session_dir=str(tmp_path))


@pytest.mark.parametrize(
    "graph", [{"root": ["root"]}, {"root": ["child"], "child": ["root"]}]
)
def test_cyclic_child_path_is_rejected_without_modifying_files(tmp_path, graph):
    store = write_graph(tmp_path, graph)
    before = {path.name: path.read_bytes() for path in tmp_path.glob("*.json")}

    with pytest.raises(ValueError, match="Cycle.*root"):
        store.get_session_tree("root")

    assert {path.name: path.read_bytes() for path in tmp_path.glob("*.json")} == before


def test_valid_chain_longer_than_python_recursion_limit(tmp_path):
    store = HierarchicalSessionStore(session_dir=str(tmp_path))
    depth = sys.getrecursionlimit() + 20
    store.create_session(session_id="node0")
    for index in range(1, depth):
        store.create_session(session_id=f"node{index}", parent_id=f"node{index - 1}")

    tree = store.get_session_tree("node0")

    for index in range(depth):
        assert tree["session_id"] == f"node{index}"
        assert tree["message_count"] == 0
        assert len(tree["children"]) == (1 if index < depth - 1 else 0)
        if tree["children"]:
            tree = tree["children"][0]


def test_branch_order_and_repeated_descendant_are_preserved(tmp_path):
    store = write_graph(
        tmp_path,
        {"root": ["left", "right", "left"], "left": ["leaf"], "right": ["leaf"], "leaf": []},
    )

    tree = store.get_session_tree("root")

    assert [child["session_id"] for child in tree["children"]] == ["left", "right", "left"]
    for child in tree["children"]:
        assert child["title"] == child["session_id"]
        assert child["children"] == [
            {"session_id": "leaf", "title": "leaf", "message_count": 0, "children": []}
        ]


def test_leaf_message_count_and_missing_child_keep_existing_shape(tmp_path):
    store = write_graph(tmp_path, {"root": ["missing"]})
    assert store.add_message("root", "user", "hello")

    assert store.get_session_tree("root") == {
        "session_id": "root", "title": "root", "message_count": 1,
        "children": [{"session_id": "missing", "title": None, "message_count": 0, "children": []}],
    }
