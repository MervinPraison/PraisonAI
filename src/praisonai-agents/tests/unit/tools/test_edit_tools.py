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

    def test_invalid_mode_behaves_like_auto(self, tmp_path):
        # Behaviour-based check: an invalid mode must act exactly like ``auto``
        # (surface diagnostics on a broken edit) rather than only matching an
        # internal field.
        editor = EditTools(post_edit_diagnostics="bogus")
        p = tmp_path / "broken.py"
        _write(p, "x = 1\n")
        result = editor.edit_file(str(p), "x = 1", "def (:")
        assert "Success" in result
        assert "Diagnostics" in result

    def test_on_mode_clean_edit_reports_no_problems(self, tmp_path):
        # ``on`` mode appends a diagnostics section even for a clean edit.
        editor = EditTools(post_edit_diagnostics="on")
        p = tmp_path / "ok.py"
        _write(p, "x = 1\n")
        result = editor.edit_file(str(p), "x = 1", "x = 2")
        assert "Success" in result
        assert "Diagnostics" in result
        assert "no problems found" in result

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


class TestPostEditFormat:
    """Post-edit formatting hook, symmetric to post-edit diagnostics."""

    def test_off_mode_is_default_and_never_formats(self, tmp_path, monkeypatch):
        # Default mode is "off": no formatter command is ever resolved or run.
        editor = EditTools()
        assert editor._post_edit_format == "off"

        called = {"resolve": False, "apply": False}

        def _resolve(self, safe_path):
            called["resolve"] = True
            return ("fake", ["fake", safe_path])

        def _apply(self, safe_path):
            called["apply"] = True

        monkeypatch.setattr(EditTools, "_format_command", _resolve)
        monkeypatch.setattr(EditTools, "_apply_post_edit_format", _apply)

        p = tmp_path / "a.py"
        _write(p, "x = 1\n")
        result = editor.edit_file(str(p), "x = 1", "x = 2")
        assert "Success" in result
        assert called == {"resolve": False, "apply": False}

    def test_invalid_mode_falls_back_to_off(self):
        editor = EditTools(post_edit_format="bogus")
        assert editor._post_edit_format == "off"

    def test_auto_mode_runs_formatter_on_edit(self, tmp_path, monkeypatch):
        # With a (stubbed) formatter available, an edit invokes it on the file.
        # Diagnostics off so the only subprocess.run is the formatter.
        editor = EditTools(post_edit_format="auto", post_edit_diagnostics="off")
        seen = {}

        def _resolve(self, safe_path):
            return ("stub", ["stub-formatter", safe_path])

        def _run(argv, **kwargs):
            # Simulate a formatter rewriting the file to canonical style.
            with open(argv[-1], "w", encoding="utf-8") as f:
                f.write("x = 2\n")
            seen["argv"] = argv
            class _P:
                returncode = 0
                stdout = ""
                stderr = ""
            return _P()

        monkeypatch.setattr(EditTools, "_format_command", _resolve)
        import subprocess
        monkeypatch.setattr(subprocess, "run", _run)

        p = tmp_path / "a.py"
        _write(p, "x=1\n")
        result = editor.edit_file(str(p), "x=1", "x=2")
        assert "Success" in result
        assert seen["argv"][0] == "stub-formatter"
        assert _read(p) == "x = 2\n"

    def test_missing_formatter_leaves_edit_successful(self, tmp_path, monkeypatch):
        # No formatter available -> edit still succeeds, file unformatted.
        editor = EditTools(post_edit_format="auto")
        monkeypatch.setattr(EditTools, "_format_command", lambda self, p: None)
        p = tmp_path / "a.py"
        _write(p, "x=1\n")
        result = editor.edit_file(str(p), "x=1", "x=2")
        assert "Success" in result
        assert _read(p) == "x=2\n"

    def test_failing_formatter_never_fails_edit(self, tmp_path, monkeypatch):
        # A formatter that raises must not turn a successful edit into an error.
        editor = EditTools(post_edit_format="auto", post_edit_diagnostics="off")
        monkeypatch.setattr(EditTools, "_format_command",
                            lambda self, p: ("boom", ["boom", p]))

        def _boom(argv, **kwargs):
            raise OSError("formatter exploded")

        import subprocess
        monkeypatch.setattr(subprocess, "run", _boom)
        p = tmp_path / "a.py"
        _write(p, "x=1\n")
        result = editor.edit_file(str(p), "x=1", "x=2")
        assert "Success" in result
        assert "Error" not in result

    def test_custom_formatter_override_with_placeholder(self, tmp_path):
        # A caller-supplied formatter map resolves the right (name, argv),
        # substituting the {path} placeholder.
        editor = EditTools(
            post_edit_format="auto",
            formatters={".py": ("myfmt", ["/usr/bin/env", "echo", "{path}"])},
        )
        cmd = editor._format_command(str(tmp_path / "a.py"))
        assert cmd is not None
        name, argv = cmd
        assert name == "myfmt"
        assert argv[0] == "/usr/bin/env"
        assert argv[-1] == str(tmp_path / "a.py")

    def test_override_appends_path_when_no_placeholder(self, tmp_path):
        editor = EditTools(
            post_edit_format="auto",
            formatters={".py": ("myfmt", ["/usr/bin/env", "echo"])},
        )
        cmd = editor._format_command(str(tmp_path / "a.py"))
        assert cmd is not None
        _name, argv = cmd
        assert argv[-1] == str(tmp_path / "a.py")

    def test_override_missing_binary_returns_none(self, tmp_path, monkeypatch):
        # Deterministic: stub the binary lookup so the result never depends on
        # host PATH state.
        import shutil
        monkeypatch.setattr(shutil, "which", lambda _name: None)
        editor = EditTools(
            post_edit_format="auto",
            formatters={".py": ("nope", ["this-binary-does-not-exist-xyz"])},
        )
        assert editor._format_command(str(tmp_path / "a.py")) is None

    def test_relative_override_resolves_from_file_dir(self, tmp_path, monkeypatch):
        # A project-local relative command (e.g. ./node_modules/.bin/prettier)
        # that exists next to the edited file should resolve, not be skipped.
        import shutil
        monkeypatch.setattr(shutil, "which", lambda _name: None)
        bindir = tmp_path / "node_modules" / ".bin"
        bindir.mkdir(parents=True)
        exe = bindir / "prettier"
        exe.write_text("#!/bin/sh\n")
        exe.chmod(0o755)
        editor = EditTools(
            post_edit_format="auto",
            formatters={".py": ("local", ["./node_modules/.bin/prettier"])},
        )
        cmd = editor._format_command(str(tmp_path / "a.py"))
        assert cmd is not None
        assert cmd[0] == "local"

    def test_failing_formatter_does_not_corrupt_baseline(self, tmp_path, monkeypatch):
        # A non-zero formatter exit (possibly leaving partial output) must NOT
        # be adopted as the clean baseline: a follow-up edit must still match
        # the known-good post-edit content rather than fail with stale-content.
        editor = EditTools(post_edit_format="auto", post_edit_diagnostics="off")
        monkeypatch.setattr(EditTools, "_format_command",
                            lambda self, p: ("stub", ["stub", p]))

        def _run(argv, **kwargs):
            # Simulate a formatter that writes garbage then exits non-zero.
            with open(argv[-1], "w", encoding="utf-8") as f:
                f.write("PARTIAL_GARBAGE")
            class _P:
                returncode = 1
                stdout = ""
                stderr = "boom"
            return _P()

        import subprocess
        monkeypatch.setattr(subprocess, "run", _run)
        p = tmp_path / "a.py"
        _write(p, "x=1\n")
        result = editor.edit_file(str(p), "x=1", "x=2")
        assert "Success" in result
        # The recorded baseline must still be the known-good post-edit content,
        # not the formatter's partial garbage, so a follow-up edit keyed on the
        # cached hash is unaffected by the failed formatter.
        assert editor._file_cache[str(p)] == editor._compute_content_hash("x=2\n")

    def test_hash_refreshed_after_successful_format(self, tmp_path, monkeypatch):
        # After a successful format, the cached hash matches the formatted
        # on-disk content so a subsequent edit is not falsely flagged as stale.
        editor = EditTools(post_edit_format="auto", post_edit_diagnostics="off")
        monkeypatch.setattr(EditTools, "_format_command",
                            lambda self, p: ("stub", ["stub", p]))

        def _run(argv, **kwargs):
            with open(argv[-1], "w", encoding="utf-8") as f:
                f.write("x = 2\n")
            class _P:
                returncode = 0
                stdout = ""
                stderr = ""
            return _P()

        import subprocess
        monkeypatch.setattr(subprocess, "run", _run)
        p = tmp_path / "a.py"
        _write(p, "x=1\n")
        first = editor.edit_file(str(p), "x=1", "x=2")
        assert "Success" in first
        assert editor._file_cache[str(p)] == editor._compute_content_hash("x = 2\n")
        # Follow-up edit against the formatted content still succeeds.
        second = editor.edit_file(str(p), "x = 2", "x = 3")
        assert "Success" in second

    def test_format_then_diagnostics_keep_edit_successful(self, tmp_path, monkeypatch):
        # Apply-patch path also formats the touched file without failing.
        editor = EditTools(post_edit_format="auto", post_edit_diagnostics="off")
        monkeypatch.setattr(EditTools, "_format_command",
                            lambda self, p: ("stub", ["stub", p]))

        def _run(argv, **kwargs):
            with open(argv[-1], "w", encoding="utf-8") as f:
                f.write("value = 2\n")
            class _P:
                returncode = 0
                stdout = ""
                stderr = ""
            return _P()

        import subprocess
        monkeypatch.setattr(subprocess, "run", _run)

        p = tmp_path / "mod.py"
        _write(p, "value = 1\n")
        patch = (
            "*** Update File: {path}\n"
            "@@\n"
            "value = 1\n"
            "===\n"
            "value = 2\n"
        ).format(path=str(p))
        result = editor.apply_patch(patch)
        assert "Success" in result
        assert _read(p) == "value = 2\n"


class TestLSPDiagnostics:
    """The post-edit diagnostics hook is wired to the existing LSP client."""

    def test_off_mode_skips_lsp(self, tmp_path, monkeypatch):
        # ``off`` short-circuits before any LSP attempt (zero overhead).
        editor = EditTools(post_edit_diagnostics="off")
        called = {"n": 0}

        def _spy(self, safe_path, display_path):
            called["n"] += 1
            return None

        monkeypatch.setattr(EditTools, "_try_lsp_diagnostics", _spy)
        p = tmp_path / "x.py"
        _write(p, "x = 1\n")
        result = editor.edit_file(str(p), "x = 1", "x = 2")
        assert "Diagnostics" not in result
        assert called["n"] == 0

    def test_no_server_falls_back_to_checker(self, tmp_path):
        # With no language server installed for the extension, LSP returns None
        # and the legacy per-language checker still surfaces syntax errors.
        editor = EditTools(post_edit_diagnostics="auto")
        # No server is configured for an unknown extension -> None.
        assert editor._try_lsp_diagnostics(str(tmp_path / "f.unknownext"), "f") is None
        p = tmp_path / "broken.py"
        _write(p, "x = 1\n")
        result = editor.edit_file(str(p), "x = 1", "def (:")
        assert "Success" in result
        assert "Diagnostics" in result

    def test_lsp_block_used_when_available(self, tmp_path, monkeypatch):
        # When the LSP path returns a formatted block, it is used verbatim and
        # the legacy checker is not consulted.
        editor = EditTools(post_edit_diagnostics="auto")

        def _fake_lsp(self, safe_path, display_path):
            return f"\n\nDiagnostics (lsp:typescript):\n{display_path}:1:1: error: oops"

        def _boom(self, safe_path):
            raise AssertionError("checker fallback should not run when LSP returns a block")

        monkeypatch.setattr(EditTools, "_try_lsp_diagnostics", _fake_lsp)
        monkeypatch.setattr(EditTools, "_diagnostics_command", staticmethod(_boom))
        p = tmp_path / "a.ts"
        _write(p, "const x = 1;\n")
        result = editor.edit_file(str(p), "const x = 1;", "const y = 2;")
        assert "Success" in result
        assert "Diagnostics (lsp:typescript)" in result

    def test_lsp_no_problems_auto_is_silent(self, tmp_path, monkeypatch):
        # An LSP run with no diagnostics in ``auto`` mode appends nothing.
        editor = EditTools(post_edit_diagnostics="auto")
        monkeypatch.setattr(
            EditTools, "_try_lsp_diagnostics",
            lambda self, safe_path, display_path: "",
        )
        p = tmp_path / "a.ts"
        _write(p, "const x = 1;\n")
        result = editor.edit_file(str(p), "const x = 1;", "const y = 2;")
        assert "Success" in result
        assert "Diagnostics" not in result

    def test_lsp_failure_falls_back_to_checker(self, tmp_path, monkeypatch):
        # A raising LSP attempt must not break the edit; the checker fallback
        # still runs and surfaces the Python syntax error.
        editor = EditTools(post_edit_diagnostics="auto")

        def _raise(self, safe_path, display_path):
            raise RuntimeError("server crashed")

        monkeypatch.setattr(EditTools, "_try_lsp_diagnostics", _raise)
        p = tmp_path / "broken.py"
        _write(p, "x = 1\n")
        result = editor.edit_file(str(p), "x = 1", "def (:")
        assert "Success" in result
        assert "Diagnostics" in result

    def test_lsp_unpublished_falls_back_to_checker(self, tmp_path, monkeypatch):
        # Regression: when an installed server starts/opens but never publishes
        # diagnostics within the budget (still indexing, debounced, or URI
        # mismatch), the LSP path must return None (not "") so the legacy
        # checker still runs and surfaces a real syntax error rather than
        # reporting a false all-clear.
        import asyncio
        from praisonaiagents.tools import edit_tools as et

        editor = EditTools(post_edit_diagnostics="auto")

        class _FakeClient:
            def __init__(self, *a, **k):
                self.config = type("C", (), {"timeout": 5})()
                self._diagnostics = {}  # server never publishes

            async def start(self):
                return True

            async def open_document(self, path):
                return True

            async def get_diagnostics(self, path):
                return []

            async def close_document(self, path):
                return None

            async def stop(self):
                return None

        monkeypatch.setattr(et, "_DIAGNOSTICS_TIMEOUT", 0.3, raising=False)
        import shutil
        monkeypatch.setattr(shutil, "which",
                            lambda cmd: "/usr/bin/" + cmd, raising=False)
        monkeypatch.setattr(
            "praisonaiagents.lsp.config.DEFAULT_SERVERS",
            {"python": {"command": "pyright-langserver", "args": []}},
            raising=False,
        )
        monkeypatch.setattr(
            "praisonaiagents.lsp.client.LSPClient", _FakeClient, raising=False
        )

        # No running loop -> the sync path uses asyncio.run; force fresh loop.
        try:
            asyncio.get_running_loop()
            pytest.skip("running loop present; sync LSP path not exercised")
        except RuntimeError:
            pass

        block = editor._try_lsp_diagnostics(str(tmp_path / "broken.py"), "broken.py")
        assert block is None  # unpublished -> fall back, not a false all-clear

    def test_lsp_clean_publish_is_authoritative(self, tmp_path, monkeypatch):
        # A genuine clean publish ([]) returns "" in auto mode and does NOT
        # redundantly run the subprocess checker.
        import asyncio
        from praisonaiagents.tools import edit_tools as et

        editor = EditTools(post_edit_diagnostics="auto")
        uri_holder = {}

        class _FakeClient:
            def __init__(self, *a, **k):
                self.config = type("C", (), {"timeout": 5})()
                self._diagnostics = uri_holder

            async def start(self):
                return True

            async def open_document(self, path):
                uri_holder[f"file://{os.path.abspath(path)}"] = []
                return True

            async def get_diagnostics(self, path):
                return []

            async def close_document(self, path):
                return None

            async def stop(self):
                return None

        import shutil
        monkeypatch.setattr(shutil, "which",
                            lambda cmd: "/usr/bin/" + cmd, raising=False)
        monkeypatch.setattr(
            "praisonaiagents.lsp.config.DEFAULT_SERVERS",
            {"python": {"command": "pyright-langserver", "args": []}},
            raising=False,
        )
        monkeypatch.setattr(
            "praisonaiagents.lsp.client.LSPClient", _FakeClient, raising=False
        )

        try:
            asyncio.get_running_loop()
            pytest.skip("running loop present; sync LSP path not exercised")
        except RuntimeError:
            pass

        block = editor._try_lsp_diagnostics(str(tmp_path / "ok.py"), "ok.py")
        assert block == ""  # published-and-clean -> authoritative all-clear


class TestAutomaticStaleness:
    def test_edit_aborts_when_changed_after_read(self, tools, tmp_path):
        p = tmp_path / "a.py"
        _write(p, "x = 1\n")
        # Read via the tool records the content hash automatically.
        content, _ = tools.read_file(str(p))
        assert content == "x = 1\n"
        # An external process changes the file after the read.
        _write(p, "x = 999\n")
        # The edit must abort by default without any expected_hash being passed.
        result = tools.edit_file(str(p), "x = 999", "x = 2")
        assert "changed since it was read" in result
        # File is untouched.
        assert _read(p) == "x = 999\n"

    def test_force_bypasses_staleness(self, tools, tmp_path):
        p = tmp_path / "a.py"
        _write(p, "x = 1\n")
        tools.read_file(str(p))
        _write(p, "x = 999\n")
        result = tools.edit_file(str(p), "x = 999", "x = 2", force=True)
        assert "Success" in result
        assert _read(p) == "x = 2\n"

    def test_no_recorded_read_allows_edit(self, tools, tmp_path):
        # Without a prior read, the default path behaves exactly as before.
        p = tmp_path / "a.py"
        _write(p, "x = 1\n")
        result = tools.edit_file(str(p), "x = 1", "x = 2")
        assert "Success" in result
        assert _read(p) == "x = 2\n"

    def test_consecutive_edits_not_flagged_stale(self, tools, tmp_path):
        # An edit updates the recorded hash so a follow-up edit is not stale.
        p = tmp_path / "a.py"
        _write(p, "a = 1\nb = 2\n")
        tools.read_file(str(p))
        assert "Success" in tools.edit_file(str(p), "a = 1", "a = 10")
        assert "Success" in tools.edit_file(str(p), "b = 2", "b = 20")
        assert _read(p) == "a = 10\nb = 20\n"

    def test_explicit_hash_still_honoured(self, tools, tmp_path):
        p = tmp_path / "a.py"
        _write(p, "x = 1\n")
        result = tools.edit_file(str(p), "x = 1", "x = 2",
                                 expected_hash="deadbeef")
        assert "modified since last read" in result

    def test_apply_patch_update_aborts_when_stale(self, tools, tmp_path):
        target = tmp_path / "u.py"
        _write(target, "def foo():\n    return 1\n")
        tools.read_file(str(target))
        _write(target, "def foo():\n    return 1\n# changed\n")
        patch = (
            f"*** Update File: {target}\n"
            "@@\n"
            "    return 1\n"
            "===\n"
            "    return 2\n"
        )
        result = tools.apply_patch(patch)
        assert "changed" in result
        assert "return 2" not in _read(target)

    def test_apply_patch_force_bypasses_staleness(self, tools, tmp_path):
        target = tmp_path / "u.py"
        _write(target, "def foo():\n    return 1\n")
        tools.read_file(str(target))
        _write(target, "def foo():\n    return 1\n# changed\n")
        patch = (
            f"*** Update File: {target}\n"
            "@@\n"
            "    return 1\n"
            "===\n"
            "    return 2\n"
        )
        result = tools.apply_patch(patch, force=True)
        assert "Success" in result
        assert "return 2" in _read(target)

    def test_apply_patch_crlf_consecutive_edits_not_stale(self, tools, tmp_path):
        # Regression: apply_patch on a CRLF file must record the on-disk
        # (CRLF-preserved) hash so a follow-up edit is not falsely flagged stale.
        p = tmp_path / "crlf.py"
        p.write_bytes(b"a = 1\r\nb = 2\r\n")
        tools.read_file(str(p))
        patch = (
            f"*** Update File: {p}\n"
            "@@\n"
            "a = 1\n"
            "===\n"
            "a = 10\n"
        )
        assert "Success" in tools.apply_patch(patch)
        # CRLF preserved on disk.
        assert p.read_bytes() == b"a = 10\r\nb = 2\r\n"
        # Follow-up edit must not be flagged stale despite the CRLF endings.
        result = tools.edit_file(str(p), "b = 2", "b = 20")
        assert "Success" in result
        assert p.read_bytes() == b"a = 10\r\nb = 20\r\n"

    def test_apply_patch_delete_aborts_when_stale(self, tools, tmp_path):
        # Regression: a destructive delete must not silently remove a file that
        # changed on disk since it was last read.
        p = tmp_path / "d.py"
        _write(p, "keep = 1\n")
        tools.read_file(str(p))
        _write(p, "keep = 1\n# changed externally\n")
        patch = f"*** Delete File: {p}\n"
        result = tools.apply_patch(patch)
        assert "changed" in result
        assert os.path.exists(str(p))
        # force=True overrides and deletes.
        assert "Success" in tools.apply_patch(patch, force=True)
        assert not os.path.exists(str(p))


class TestConcurrency:
    def test_concurrent_edits_serialise_same_file(self, tools, tmp_path):
        import threading
        import contextvars

        p = tmp_path / "counter.txt"
        # Start with N distinct tokens; each thread replaces one token. Under a
        # correct per-file lock every replacement lands without corruption.
        # Zero-pad so no token is a substring of another (avoids ambiguity).
        n = 25
        _write(p, "".join(f"T{i:03d}\n" for i in range(n)))

        errors = []

        def worker(i):
            try:
                res = tools.edit_file(str(p), f"T{i:03d}", f"D{i:03d}", force=True)
                if "Success" not in res:
                    errors.append(res)
            except Exception as e:  # pragma: no cover - defensive
                errors.append(str(e))

        # Copy the current context (carrying the auto-approval) into each
        # worker thread so the high-risk edit_file runs non-interactively.
        threads = [
            threading.Thread(target=contextvars.copy_context().run, args=(worker, i))
            for i in range(n)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, errors
        out = _read(p)
        # Every token must have been replaced exactly once; no line lost/merged.
        for i in range(n):
            assert f"D{i:03d}\n" in out
            assert f"T{i:03d}\n" not in out

    def test_different_files_use_different_locks(self, tools, tmp_path):
        from praisonaiagents.tools import _file_locks

        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        _write(a, "a\n")
        _write(b, "b\n")
        lock_a = _file_locks.get_lock(tools._validate_path(str(a)))
        lock_b = _file_locks.get_lock(tools._validate_path(str(b)))
        assert lock_a is not lock_b
        # Same path returns the same lock object (shared across callers).
        assert lock_a is _file_locks.get_lock(tools._validate_path(str(a)))
