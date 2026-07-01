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
        assert file_tools.read_file("s.txt", line_numbers=False) == "v1"
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


def test_read_file_line_numbers_by_default():
    from praisonaiagents.workspace import Workspace
    from praisonaiagents.tools.file_tools import FileTools

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Workspace(root=Path(tmpdir))
        file_tools = FileTools(workspace=workspace)
        target = Path(tmpdir) / "code.py"
        target.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

        out = file_tools.read_file("code.py")
        lines = out.split("\n")
        assert lines[0].endswith("\talpha")
        assert lines[0].strip().startswith("1")
        assert lines[1].endswith("\tbeta")
        assert lines[2].endswith("\tgamma")


def test_read_file_raw_whole_file_unchanged():
    from praisonaiagents.workspace import Workspace
    from praisonaiagents.tools.file_tools import FileTools

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Workspace(root=Path(tmpdir))
        file_tools = FileTools(workspace=workspace)
        target = Path(tmpdir) / "c.txt"
        target.write_text("one\ntwo\nthree\n", encoding="utf-8")

        # line_numbers=False with no window returns the exact original content.
        assert file_tools.read_file("c.txt", line_numbers=False) == "one\ntwo\nthree\n"


def test_read_file_offset_and_limit_window():
    from praisonaiagents.workspace import Workspace
    from praisonaiagents.tools.file_tools import FileTools

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Workspace(root=Path(tmpdir))
        file_tools = FileTools(workspace=workspace)
        target = Path(tmpdir) / "big.txt"
        target.write_text("\n".join(f"line{i}" for i in range(1, 11)) + "\n",
                          encoding="utf-8")

        out = file_tools.read_file("big.txt", offset=3, limit=2, line_numbers=False)
        # Raw window preserves original line endings byte-for-byte.
        assert out.startswith("line3\nline4\n")
        # More lines remain after the window -> paging hint present.
        assert "call again with offset=5" in out

        numbered = file_tools.read_file("big.txt", offset=3, limit=2)
        body_lines = numbered.split("\n")
        assert body_lines[0].endswith("\tline3")
        assert body_lines[0].strip().startswith("3")
        assert body_lines[1].endswith("\tline4")

        # A window that reaches EOF has no paging hint; raw window keeps the
        # file's own trailing newline.
        tail = file_tools.read_file("big.txt", offset=9, limit=2, line_numbers=False)
        assert tail == "line9\nline10\n"


def test_read_file_truncation_hint():
    from praisonaiagents.workspace import Workspace
    from praisonaiagents.tools.file_tools import FileTools

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Workspace(root=Path(tmpdir))
        file_tools = FileTools(workspace=workspace)
        target = Path(tmpdir) / "big.txt"
        target.write_text("\n".join(f"line{i}" for i in range(1, 11)) + "\n",
                          encoding="utf-8")

        out = file_tools.read_file("big.txt", offset=1, limit=4)
        assert "showing lines 1-4 of 10" in out
        assert "offset=5" in out


def test_read_file_default_line_cap():
    from praisonaiagents.tools import file_tools as ft_module
    from praisonaiagents.workspace import Workspace
    from praisonaiagents.tools.file_tools import FileTools

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Workspace(root=Path(tmpdir))
        file_tools = FileTools(workspace=workspace)
        target = Path(tmpdir) / "huge.txt"
        n = ft_module.DEFAULT_MAX_LINES + 50
        target.write_text("\n".join(f"l{i}" for i in range(n)) + "\n",
                          encoding="utf-8")

        out = file_tools.read_file("huge.txt")
        assert f"call again with offset={ft_module.DEFAULT_MAX_LINES + 1}" in out


def test_read_file_per_line_char_cap():
    from praisonaiagents.workspace import Workspace
    from praisonaiagents.tools.file_tools import FileTools

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Workspace(root=Path(tmpdir))
        file_tools = FileTools(workspace=workspace)
        target = Path(tmpdir) / "long.txt"
        target.write_text("x" * 5000 + "\nshort\n", encoding="utf-8")

        out = file_tools.read_file("long.txt", max_line_chars=100)
        assert "(line truncated)" in out


def test_read_file_raw_window_keeps_newlines():
    # A raw windowed read (line_numbers=False + offset/limit) preserves the
    # within-window newlines (via splitlines(keepends=True)) so the slice keeps
    # its structure. Text-mode reads normalise CRLF->LF as before; the paging
    # hint is separated from body content by exactly one newline.
    from praisonaiagents.workspace import Workspace
    from praisonaiagents.tools.file_tools import FileTools

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Workspace(root=Path(tmpdir))
        file_tools = FileTools(workspace=workspace)
        target = Path(tmpdir) / "crlf.txt"
        target.write_bytes(b"alpha\r\nbeta\r\ngamma\r\n")

        out = file_tools.read_file("crlf.txt", offset=1, limit=2, line_numbers=False)
        # Body keeps its per-line newlines; hint is not glued with a blank line.
        assert out.startswith("alpha\nbeta\n")
        assert "\n\n..." not in out
        assert "call again with offset=3 for more" in out


def test_read_file_negative_limit_returns_empty_window():
    # A negative limit is an invalid bound and must not silently expand to the
    # default cap; the window should be empty.
    from praisonaiagents.workspace import Workspace
    from praisonaiagents.tools.file_tools import FileTools

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Workspace(root=Path(tmpdir))
        file_tools = FileTools(workspace=workspace)
        target = Path(tmpdir) / "n.txt"
        target.write_text("a\nb\nc\n", encoding="utf-8")

        out = file_tools.read_file("n.txt", offset=1, limit=-1, line_numbers=False)
        assert out.startswith("... (showing lines 1-0 of 3;")


def test_read_file_negative_max_line_chars_leaves_line_intact():
    # A negative max_line_chars must not truncate lines backwards.
    from praisonaiagents.workspace import Workspace
    from praisonaiagents.tools.file_tools import FileTools

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Workspace(root=Path(tmpdir))
        file_tools = FileTools(workspace=workspace)
        target = Path(tmpdir) / "long.txt"
        target.write_text("x" * 50 + "\n", encoding="utf-8")

        out = file_tools.read_file("long.txt", max_line_chars=-1)
        assert "(line truncated)" not in out
        assert "x" * 50 in out


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
        assert file_tools.read_file("s.txt", line_numbers=False) == "v1"

        def _boom(*args, **kwargs):
            raise OSError("cannot read for verification")

        monkeypatch.setattr(FileTools, "_content_hash", staticmethod(_boom))
        # Verification read fails -> write refused, file untouched.
        assert file_tools.write_file("s.txt", "v2") is False
        assert target.read_text(encoding="utf-8") == "v1"
