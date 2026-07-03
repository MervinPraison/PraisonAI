"""Tests for the agent-callable LSP navigation built-in tools.

Covers:
1. Registration / lazy import via ``praisonaiagents.tools``.
2. Path safety (traversal rejection, missing file).
3. Graceful degradation when no language server is installed.
4. Compact result formatting helpers.
5. An optional live pylsp integration test proving ``lsp_references`` resolves
   symbols more precisely than a naive text grep.
"""

import os
import shutil
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_lsp_tools_are_registered():
    from praisonaiagents.tools import (
        lsp_definition, lsp_references, lsp_hover,
        lsp_document_symbols, lsp_workspace_symbols,
    )
    for fn in (lsp_definition, lsp_references, lsp_hover,
               lsp_document_symbols, lsp_workspace_symbols):
        assert callable(fn)


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------

def test_missing_file_reports_error(tmp_path, monkeypatch):
    from praisonaiagents.tools import lsp_definition
    monkeypatch.chdir(tmp_path)
    out = lsp_definition("does_not_exist.py", symbol="foo")
    assert out.startswith("Error:")
    assert "not found" in out


def test_path_traversal_rejected(tmp_path, monkeypatch):
    from praisonaiagents.tools import lsp_references
    monkeypatch.chdir(tmp_path)
    out = lsp_references("../../etc/passwd", symbol="root")
    assert out.startswith("Error:")


def test_unknown_language_reports_error(tmp_path, monkeypatch):
    from praisonaiagents.tools import lsp_document_symbols
    (tmp_path / "notes.txt").write_text("hello\n")
    monkeypatch.chdir(tmp_path)
    out = lsp_document_symbols("notes.txt")
    assert out.startswith("Error:")
    assert "language server" in out


# ---------------------------------------------------------------------------
# Graceful degradation (no server installed)
# ---------------------------------------------------------------------------

def test_degrades_when_server_not_installed(tmp_path, monkeypatch):
    from praisonaiagents.tools import lsp_definition
    (tmp_path / "mod.py").write_text("def foo():\n    return 1\n")
    monkeypatch.chdir(tmp_path)
    # Force "no server installed" regardless of the CI image.
    with patch("shutil.which", return_value=None):
        out = lsp_definition("mod.py", symbol="foo")
    assert out.startswith("Error:")
    assert "not installed" in out


def test_workspace_symbols_requires_query():
    from praisonaiagents.tools import lsp_workspace_symbols
    assert lsp_workspace_symbols("").startswith("Error:")


def test_workspace_symbols_degrades_without_server(tmp_path, monkeypatch):
    from praisonaiagents.tools import lsp_workspace_symbols
    monkeypatch.chdir(tmp_path)
    with patch("shutil.which", return_value=None):
        out = lsp_workspace_symbols("foo")
    assert out.startswith("Error:")
    assert "not installed" in out


# ---------------------------------------------------------------------------
# Position resolution & formatting helpers
# ---------------------------------------------------------------------------

def test_resolve_position_by_symbol(tmp_path):
    from praisonaiagents.tools import lsp_tools
    f = tmp_path / "mod.py"
    f.write_text("x = 1\ndef target():\n    return x\n")
    line, char, err = lsp_tools._resolve_position(str(f), None, None, "target")
    assert err is None
    assert line == 1
    assert char == f.read_text().splitlines()[1].index("target")


def test_resolve_position_symbol_missing(tmp_path):
    from praisonaiagents.tools import lsp_tools
    f = tmp_path / "mod.py"
    f.write_text("x = 1\n")
    _, _, err = lsp_tools._resolve_position(str(f), None, None, "nope")
    assert err is not None
    assert "not found" in err


def test_resolve_position_requires_input(tmp_path):
    from praisonaiagents.tools import lsp_tools
    f = tmp_path / "mod.py"
    f.write_text("x = 1\n")
    _, _, err = lsp_tools._resolve_position(str(f), None, None, None)
    assert err is not None


def test_format_locations_empty():
    from praisonaiagents.tools import lsp_tools
    assert "none found" in lsp_tools._format_locations([], "References")


def test_format_symbols_document(tmp_path):
    from praisonaiagents.tools import lsp_tools
    symbols = [
        {"name": "foo", "kind": 12,
         "range": {"start": {"line": 3, "character": 0}}},
        {"name": "Bar", "kind": 5,
         "location": {"uri": "file:///x.py",
                      "range": {"start": {"line": 10, "character": 4}}}},
    ]
    out = lsp_tools._format_symbols(symbols, "Document symbols")
    assert "function foo" in out
    assert "4:1" in out  # 0-indexed line 3 -> 1-indexed 4
    assert "class Bar" in out


# ---------------------------------------------------------------------------
# Live pylsp integration (opt-in: only runs when pylsp is installed)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("pylsp") is None,
                    reason="pylsp language server not installed")
def test_references_live_pylsp(tmp_path, monkeypatch):
    from praisonaiagents.tools import lsp_references
    # A tiny package where the identifier ``compute`` is defined once and
    # called once, while a *different* string ``compute`` appears in a comment
    # and a docstring that a naive grep would over-match.
    src = (
        "def compute(x):\n"
        "    return x + 1\n"
        "\n"
        "# compute is mentioned here in a comment\n"
        "MSG = 'call compute somewhere'\n"
        "\n"
        "def caller():\n"
        "    return compute(41)\n"
    )
    f = tmp_path / "mod.py"
    f.write_text(src)
    monkeypatch.chdir(tmp_path)

    out = lsp_references("mod.py", symbol="compute")
    # The definition line and the real call site should be reported.
    assert "mod.py:1:" in out  # definition
    assert "mod.py:8:" in out  # the caller() call site
    # The comment (line 4) and string (line 5) must NOT be reported as refs.
    assert "mod.py:4:" not in out
    assert "mod.py:5:" not in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
