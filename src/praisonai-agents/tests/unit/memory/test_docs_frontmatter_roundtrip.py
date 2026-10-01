"""Documentation metadata remains text through creation and disk reload."""

import pytest

from praisonaiagents.memory.docs_manager import DocsManager


@pytest.mark.parametrize("text", [
    'Use "quoted" text',
    r"C:\new\reference",
    "first line\nsecond line",
    "before---after",
    "plain text",
    "Unicode 文档: value",
    "Unicode 😀\u0085next",
])
@pytest.mark.parametrize("field", ["description", "tags"])
def test_created_metadata_survives_reload(tmp_path, text, field):
    options = dict(workspace_path=str(tmp_path), global_docs_path=str(tmp_path / "global"))
    manager = DocsManager(**options)
    value = [text, "other"] if field == "tags" else text
    manager.create_doc("reference", "Keep this body", priority=200, **{field: value})
    manager.reload()
    reopened = DocsManager(**options)
    for current in (manager, reopened):
        doc = current.get_doc("reference")
        assert doc is not None
        assert getattr(doc, field) == value
        assert doc.content == "Keep this body"
        assert doc.priority == 200
        if field == "tags":
            assert [item.name for item in current.get_docs_by_tag(text)] == ["reference"]


def test_frontmatter_delimiters_are_complete_lines(tmp_path):
    manager = DocsManager(workspace_path=str(tmp_path), global_docs_path=str(tmp_path / "global"))
    docs_dir = tmp_path / manager.DOCS_DIR_NAME
    docs_dir.mkdir(parents=True)
    (docs_dir / "reference.md").write_text(
        '---\ndescription: "before---after"\npriority: 200\n---\nBody\n---\nMore body',
        encoding="utf-8",
    )
    manager.reload()
    doc = manager.get_doc("reference")
    assert doc.description == "before---after"
    assert doc.content == "Body\n---\nMore body"


@pytest.mark.parametrize("source", ["---\ndescription: [\n---\nBody", "---\nunfinished"])
def test_invalid_or_unclosed_frontmatter_preserves_original_text(tmp_path, source):
    manager = DocsManager(workspace_path=str(tmp_path), global_docs_path=str(tmp_path / "global"))
    docs_dir = tmp_path / manager.DOCS_DIR_NAME
    docs_dir.mkdir(parents=True)
    (docs_dir / "reference.md").write_text(source, encoding="utf-8")
    manager.reload()
    assert manager.get_doc("reference").content == source
