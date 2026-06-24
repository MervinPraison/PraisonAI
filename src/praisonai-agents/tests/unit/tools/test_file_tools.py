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


def test_filetools_read_then_edittools_edit_crlf_not_stale(_auto_approve_write):
    # Regression: FileTools.read_file (text mode) and EditTools.edit_file
    # (binary mode) must record the same on-disk hash for a CRLF file so a
    # read-by-one / edit-by-the-other chain is not falsely flagged stale.
    from praisonaiagents.workspace import Workspace
    from praisonaiagents.tools.file_tools import FileTools
    from praisonaiagents.tools.edit_tools import EditTools

    token = set_yaml_approved_tools(["write_file", "edit_file"])
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Workspace(root=Path(tmpdir))
            file_tools = FileTools(workspace=workspace)
            edit_tools = EditTools(workspace=workspace)
            target = Path(tmpdir) / "crlf.txt"
            target.write_bytes(b"alpha\r\nbeta\r\n")

            # Read via FileTools records the shared hash.
            file_tools.read_file("crlf.txt")
            # Edit via EditTools must not see it as stale (no external change).
            result = edit_tools.edit_file("crlf.txt", "alpha", "ALPHA")
            assert "Success" in result
            assert target.read_bytes() == b"ALPHA\r\nbeta\r\n"
    finally:
        reset_yaml_approved_tools(token)


def test_write_file_fails_closed_when_verify_unreadable(_auto_approve_write, monkeypatch):
    # Regression: if the staleness verification re-read raises, the write must
    # fail closed (refuse) rather than blindly clobbering the file.
    from praisonaiagents.workspace import Workspace
    from praisonaiagents.tools.file_tools import FileTools

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Workspace(root=Path(tmpdir))
        file_tools = FileTools(workspace=workspace)
        target = Path(tmpdir) / "s.txt"
        target.write_text("v1", encoding="utf-8")
        assert file_tools.read_file("s.txt") == "v1"

        def _boom(*args, **kwargs):
            raise OSError("cannot read for verification")

        monkeypatch.setattr(FileTools, "_content_hash", staticmethod(_boom))
        # Verification read fails -> write refused, file untouched.
        assert file_tools.write_file("s.txt", "v2") is False
        assert target.read_text(encoding="utf-8") == "v1"
