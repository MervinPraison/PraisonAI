from pathlib import Path
import tempfile

import pytest

from praisonaiagents.approval import (
    set_yaml_approved_tools,
    reset_yaml_approved_tools,
)


@pytest.fixture
def _auto_approve_write():
    token = set_yaml_approved_tools(["write_file"])
    try:
        yield
    finally:
        reset_yaml_approved_tools(token)


def test_get_file_info_with_workspace():
    from praisonaiagents.workspace import Workspace
    from praisonaiagents.tools.file_tools import FileTools

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Workspace(root=Path(tmpdir))
        file_tools = FileTools(workspace=workspace)
        target = Path(tmpdir) / "sample.txt"
        target.write_text("hello", encoding="utf-8")

        info = file_tools.get_file_info("sample.txt")

        assert info["name"] == "sample.txt"
        assert info["size"] == 5
        assert info["is_file"] is True


def test_write_file_aborts_when_stale(_auto_approve_write):
    from praisonaiagents.workspace import Workspace
    from praisonaiagents.tools.file_tools import FileTools

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Workspace(root=Path(tmpdir))
        file_tools = FileTools(workspace=workspace)
        target = Path(tmpdir) / "s.txt"
        target.write_text("v1", encoding="utf-8")

        # Read records the hash; an external change then makes it stale.
        assert file_tools.read_file("s.txt") == "v1"
        target.write_text("external change", encoding="utf-8")

        # Default write must refuse and leave the file untouched.
        assert file_tools.write_file("s.txt", "v2") is False
        assert target.read_text(encoding="utf-8") == "external change"

        # force=True overrides the guard.
        assert file_tools.write_file("s.txt", "v2", force=True) is True
        assert target.read_text(encoding="utf-8") == "v2"


def test_write_file_new_path_unaffected(_auto_approve_write):
    from praisonaiagents.workspace import Workspace
    from praisonaiagents.tools.file_tools import FileTools

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Workspace(root=Path(tmpdir))
        file_tools = FileTools(workspace=workspace)
        # No prior read: behaves exactly as before.
        assert file_tools.write_file("new.txt", "hi") is True
        assert (Path(tmpdir) / "new.txt").read_text(encoding="utf-8") == "hi"
