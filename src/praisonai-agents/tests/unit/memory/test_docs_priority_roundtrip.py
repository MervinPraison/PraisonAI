"""Created documentation must keep the same effective priority after reload."""

import pytest

from praisonaiagents.memory.docs_manager import DocsManager


@pytest.mark.parametrize("scope", ["workspace", "global"])
@pytest.mark.parametrize("priority", [0, -5, 200, 1500])
def test_created_doc_priority_and_selection_survive_reload(tmp_path, scope, priority):
    """Persist explicit priorities and preserve selection across manager lifecycles."""
    options = dict(workspace_path=str(tmp_path), global_docs_path=str(tmp_path / "global"))
    manager = DocsManager(**options)
    manager.create_doc("reference", "Stable documentation content", priority=priority, scope=scope)
    before_priority = manager.get_doc("reference").priority
    before_selection = [doc.name for doc in manager.get_docs_for_context()]
    manager.reload()
    reopened = DocsManager(**options)
    for current in (manager, reopened):
        assert current.get_doc("reference").priority == before_priority
        assert [doc.name for doc in current.get_docs_for_context()] == before_selection
    expected_priority = priority - 1000 if scope == "global" else priority
    assert before_priority == expected_priority


def test_new_global_doc_does_not_temporarily_outrank_workspace_doc(tmp_path):
    """Apply the global priority offset immediately when creating documents."""
    manager = DocsManager(workspace_path=str(tmp_path), global_docs_path=str(tmp_path / "global"))
    manager.create_doc("local", "local content", priority=200)
    manager.create_doc("shared", "global content", priority=300, scope="global")
    assert [doc.name for doc in manager.get_all_docs()] == ["local", "shared"]
    assert [doc.name for doc in manager.get_docs_for_context()] == ["local"]
