"""Unit tests for resilient file editing (fuzzy replace + apply_patch).

Covers the multi-strategy matching ladder in EditTools.edit_file and the
atomic multi-file apply_patch tool added for coding-agent workflows.
"""

import os
import pytest

from praisonaiagents.approval import (
    set_yaml_approved_tools,
    reset_yaml_approved_tools,
)
from praisonaiagents.tools.edit_tools import EditTools


@pytest.fixture(autouse=True)
def _auto_approve():
    """Auto-approve high-risk edit tools so tests run non-interactively."""
    token = set_yaml_approved_tools(["edit_file", "apply_patch"])
    try:
        yield
    finally:
        reset_yaml_approved_tools(token)


@pytest.fixture
def tools():
    return EditTools()


def _write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestExactMatchBackwardCompat:
    def test_exact_match_unchanged(self, tools, tmp_path):
        p = tmp_path / "a.py"
        _write(p, "def foo():\n    return 1\n")
        result = tools.edit_file(str(p), "return 1", "return 2")
        assert "Success" in result
        assert "return 2" in _read(p)

    def test_string_not_found(self, tools, tmp_path):
        p = tmp_path / "a.py"
        _write(p, "hello world\n")
        result = tools.edit_file(str(p), "nonexistent token here", "x")
        assert "String not found" in result

    def test_empty_old_string(self, tools, tmp_path):
        p = tmp_path / "a.py"
        _write(p, "hello\n")
        result = tools.edit_file(str(p), "", "x")
        assert "non-empty" in result

    def test_ambiguous_exact(self, tools, tmp_path):
        p = tmp_path / "a.py"
        _write(p, "x = 1\nx = 1\n")
        result = tools.edit_file(str(p), "x = 1", "x = 2")
        assert "Ambiguous" in result

    def test_replace_all(self, tools, tmp_path):
        p = tmp_path / "a.py"
        _write(p, "x = 1\nx = 1\n")
        result = tools.edit_file(str(p), "x = 1", "x = 2", replace_all=True)
        assert "Success" in result
        assert _read(p) == "x = 2\nx = 2\n"


class TestFuzzyMatching:
    def test_line_trimmed_indentation(self, tools, tmp_path):
        p = tmp_path / "a.py"
        _write(p, "def foo():\n        return 1\n")
        # old_string uses different indentation than file
        result = tools.edit_file(str(p), "    return 1", "    return 2")
        assert "Success" in result
        assert "return 2" in _read(p)

    def test_whitespace_normalised(self, tools, tmp_path):
        p = tmp_path / "a.py"
        _write(p, "x   =    1\n")
        result = tools.edit_file(str(p), "x = 1", "x = 99")
        assert "Success" in result
        assert "x = 99" in _read(p)

    def test_indentation_flexible_tabs(self, tools, tmp_path):
        p = tmp_path / "a.py"
        _write(p, "def foo():\n\treturn 1\n")
        result = tools.edit_file(str(p), "    return 1", "    return 2")
        assert "Success" in result
        assert "return 2" in _read(p)

    def test_block_anchor_similarity(self, tools, tmp_path):
        p = tmp_path / "a.py"
        _write(p, "def foo():\n    a = 1\n    b = 2\n    return a + b\n")
        old = "def foo():\n    a = 1\n    b = 3\n    return a + b"
        new = "def foo():\n    return 0"
        result = tools.edit_file(str(p), old, new)
        assert "Success" in result
        assert "return 0" in _read(p)

    def test_crlf_line_endings(self, tools, tmp_path):
        p = tmp_path / "a.py"
        with open(p, "wb") as f:
            f.write(b"def foo():\r\n    return 1\r\n")
        result = tools.edit_file(str(p), "    return 1", "    return 2")
        assert "Success" in result
        with open(p, "rb") as f:
            data = f.read()
        assert b"return 2" in data
        assert b"\r\n" in data

    def test_fuzzy_midfile_does_not_merge_next_line(self, tools, tmp_path):
        # Regression: fuzzy span must exclude the matched line's trailing
        # newline so the replacement does not merge with the following line.
        # (line_trimmed matches the whole "    return 1" line; the newline and
        # the following "foo" line must remain intact.)
        p = tmp_path / "a.py"
        _write(p, "    return 1\nfoo\n")
        result = tools.edit_file(str(p), "return 1", "return 2")
        assert "Success" in result
        out = _read(p)
        assert out.endswith("\nfoo\n")
        assert "return 2foo" not in out
        assert "return 2" in out


class TestFindSpanInternals:
    def test_exact_spans(self, tools):
        spans = tools._exact("abcabc", "abc")
        assert spans == [(0, 3), (3, 6)]

    def test_no_match_returns_empty(self, tools):
        assert tools._find_spans("hello", "zzz") == []

    def test_block_anchor_rejects_low_similarity(self, tools):
        content = "start\ncompletely different stuff here\nend\n"
        old = "start\naaaa bbbb cccc dddd eeee ffff\nfinish"
        spans = tools._block_anchor(content, old)
        # last anchor differs ("finish" vs "end") so no match
        assert spans == []

    def test_block_anchor_scans_all_candidates(self, tools):
        # Two blocks share the same first/last anchors; the second is an exact
        # structural match. The scanner must not break after the first anchor
        # pairing (regression for the premature-break bug).
        content = (
            "begin\n    wrong = 0\nend\n"
            "begin\n    a = 1\n    b = 2\nend\n"
        )
        old = "begin\n    a = 1\n    b = 2\nend"
        spans = tools._block_anchor(content, old)
        assert spans  # a confident span was found despite the earlier pair

    def test_fuzzy_ambiguous_reports_error(self, tools, tmp_path):
        # Identical fuzzy-matchable lines at two locations -> ambiguity error.
        p = tmp_path / "a.py"
        _write(p, "x   =   1\nother\nx   =   1\n")
        # ws-normalised matches both "x = 1" lines.
        result = tools.edit_file(str(p), "x = 1", "x = 2")
        assert "Ambiguous" in result


class TestApplyPatch:
    def test_add_file(self, tools, tmp_path):
        target = tmp_path / "new.py"
        patch = f"*** Add File: {target}\nprint('hi')\n"
        result = tools.apply_patch(patch)
        assert "Success" in result
        assert os.path.exists(target)
        assert "print('hi')" in _read(target)

    def test_add_existing_fails(self, tools, tmp_path):
        target = tmp_path / "new.py"
        _write(target, "exists\n")
        patch = f"*** Add File: {target}\nprint('hi')\n"
        result = tools.apply_patch(patch)
        assert "already exists" in result

    def test_delete_file(self, tools, tmp_path):
        target = tmp_path / "gone.py"
        _write(target, "delete me\n")
        patch = f"*** Delete File: {target}\n"
        result = tools.apply_patch(patch)
        assert "Success" in result
        assert not os.path.exists(target)

    def test_update_file(self, tools, tmp_path):
        target = tmp_path / "upd.py"
        _write(target, "def foo():\n    return 1\n")
        patch = (
            f"*** Update File: {target}\n"
            "@@\n"
            "    return 1\n"
            "===\n"
            "    return 2\n"
        )
        result = tools.apply_patch(patch)
        assert "Success" in result
        assert "return 2" in _read(target)

    def test_atomic_multi_file(self, tools, tmp_path):
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        c = tmp_path / "c.py"
        _write(b, "old content\n")
        _write(c, "to delete\n")
        patch = (
            f"*** Add File: {a}\n"
            "new file\n"
            f"*** Update File: {b}\n"
            "@@\n"
            "old content\n"
            "===\n"
            "new content\n"
            f"*** Delete File: {c}\n"
        )
        result = tools.apply_patch(patch)
        assert "Success" in result
        assert os.path.exists(a)
        assert "new content" in _read(b)
        assert not os.path.exists(c)

    def test_atomic_rollback_on_failure(self, tools, tmp_path):
        a = tmp_path / "a.py"
        b = tmp_path / "missing.py"  # does not exist -> update fails
        patch = (
            f"*** Add File: {a}\n"
            "new file\n"
            f"*** Update File: {b}\n"
            "@@\n"
            "old\n"
            "===\n"
            "new\n"
        )
        result = tools.apply_patch(patch)
        assert "Error" in result
        # Atomicity: the Add must NOT have been committed.
        assert not os.path.exists(a)

    def test_empty_patch(self, tools):
        assert "no operations" in tools.apply_patch("")

    def test_update_fuzzy_hunk(self, tools, tmp_path):
        target = tmp_path / "u.py"
        _write(target, "def foo():\n        return 1\n")
        patch = (
            f"*** Update File: {target}\n"
            "@@\n"
            "    return 1\n"
            "===\n"
            "    return 2\n"
        )
        result = tools.apply_patch(patch)
        assert "Success" in result
        assert "return 2" in _read(target)

    def test_begin_end_patch_sentinels_not_in_body(self, tools, tmp_path):
        # Regression: *** Begin/End Patch must not leak into file content.
        target = tmp_path / "wrapped.py"
        patch = (
            "*** Begin Patch\n"
            f"*** Add File: {target}\n"
            "print('hi')\n"
            "*** End Patch\n"
        )
        result = tools.apply_patch(patch)
        assert "Success" in result
        content = _read(target)
        assert "End Patch" not in content
        assert "Begin Patch" not in content
        assert content == "print('hi')"

    def test_update_preserves_crlf_and_bom(self, tools, tmp_path):
        target = tmp_path / "crlf.py"
        with open(target, "wb") as f:
            f.write(b"\xef\xbb\xbfdef foo():\r\n    return 1\r\n")
        patch = (
            f"*** Update File: {target}\n"
            "@@\n"
            "    return 1\n"
            "===\n"
            "    return 2\n"
        )
        result = tools.apply_patch(patch)
        assert "Success" in result
        with open(target, "rb") as f:
            data = f.read()
        assert data.startswith(b"\xef\xbb\xbf")  # BOM preserved
        assert b"\r\n" in data  # CRLF preserved
        assert b"return 2" in data

    def test_rollback_mid_phase2(self, tools, tmp_path, monkeypatch):
        # Force a failure on the SECOND commit and confirm the first is undone.
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        _write(b, "original b\n")
        patch = (
            f"*** Add File: {a}\n"
            "new a\n"
            f"*** Update File: {b}\n"
            "@@\n"
            "original b\n"
            "===\n"
            "updated b\n"
        )

        real_replace = os.replace
        calls = {"n": 0}

        def flaky_replace(src, dst, *args, **kwargs):
            calls["n"] += 1
            # First os.replace is the Add commit; let it through. The Update
            # commit issues further os.replace calls -> fail one of them.
            if calls["n"] == 2:
                raise OSError("simulated disk failure")
            return real_replace(src, dst, *args, **kwargs)

        monkeypatch.setattr(os, "replace", flaky_replace)
        result = tools.apply_patch(patch)
        monkeypatch.undo()

        assert "Error" in result
        # Add must have been rolled back.
        assert not os.path.exists(a)
        # Update target must retain its original content.
        assert _read(b) == "original b\n"


class TestPostEditDiagnostics:
    """Post-edit diagnostics feedback for the built-in editor."""

    def test_clean_edit_has_no_diagnostics_section_auto(self, tools, tmp_path):
        # auto mode (default): a valid edit returns the plain success string.
        p = tmp_path / "ok.py"
        _write(p, "x = 1\n")
        result = tools.edit_file(str(p), "x = 1", "x = 2")
        assert "Success" in result
        assert "Diagnostics" not in result

    def test_syntax_error_surfaces_diagnostics(self, tmp_path):
        # Editing a .py file into a syntax error must append a diagnostics block.
        editor = EditTools(post_edit_diagnostics="auto")
        p = tmp_path / "broken.py"
        _write(p, "x = 1\n")
        result = editor.edit_file(str(p), "x = 1", "def (:")
        assert "Success" in result
        assert "Diagnostics" in result

    def test_off_mode_never_runs_diagnostics(self, tmp_path):
        editor = EditTools(post_edit_diagnostics="off")
        p = tmp_path / "broken.py"
        _write(p, "x = 1\n")
        result = editor.edit_file(str(p), "x = 1", "def (:")
        assert "Success" in result
        assert "Diagnostics" not in result

    def test_missing_checker_returns_plain_success(self, tools, tmp_path):
        # An extension with no available checker yields the plain success string.
        p = tmp_path / "note.unknownext"
        _write(p, "hello\n")
        result = tools.edit_file(str(p), "hello", "world")
        assert "Success" in result
        assert "Diagnostics" not in result

    def test_invalid_mode_falls_back_to_auto(self):
        editor = EditTools(post_edit_diagnostics="bogus")
        assert editor._post_edit_diagnostics == "auto"

    def test_apply_patch_surfaces_diagnostics(self, tmp_path):
        editor = EditTools(post_edit_diagnostics="auto")
        p = tmp_path / "mod.py"
        _write(p, "value = 1\n")
        patch = (
            "*** Update File: {path}\n"
            "@@\n"
            "value = 1\n"
            "===\n"
            "def (:\n"
        ).format(path=str(p))
        result = editor.apply_patch(patch)
        assert "Success" in result
        assert "Diagnostics" in result
