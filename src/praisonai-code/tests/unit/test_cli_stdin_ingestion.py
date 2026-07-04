"""Tests for piped stdin ingestion in the modern CLI commands (issue #2656).

`praisonai run`/`code`/`chat` must read piped stdin so they compose in Unix
pipelines and CI, matching the legacy bare-prompt path. Reading must be
non-blocking/EOF-safe so an interactive TTY is never stalled.
"""

import io

import pytest

from praisonai_code.cli.utils import stdin as stdin_util


class _FakeStdin(io.StringIO):
    """StringIO that also reports whether it is a TTY."""

    def __init__(self, content="", isatty=False):
        super().__init__(content)
        self._isatty = isatty

    def isatty(self):
        return self._isatty


def _patch_stdin(monkeypatch, content, *, isatty=False, has_data=True):
    fake = _FakeStdin(content, isatty=isatty)
    monkeypatch.setattr(stdin_util.sys, "stdin", fake)
    # Force select() to report data available (or not) deterministically.
    import select

    monkeypatch.setattr(
        select, "select", lambda r, w, x, t: (list(r) if has_data else [], [], [])
    )
    return fake


def test_read_stdin_returns_none_for_tty(monkeypatch):
    _patch_stdin(monkeypatch, "ignored", isatty=True)
    assert stdin_util.read_stdin_if_available() is None


def test_read_stdin_returns_piped_content(monkeypatch):
    _patch_stdin(monkeypatch, "  piped data  ")
    assert stdin_util.read_stdin_if_available() == "piped data"


def test_read_stdin_returns_none_when_empty(monkeypatch):
    _patch_stdin(monkeypatch, "   ")
    assert stdin_util.read_stdin_if_available() is None


def test_read_stdin_returns_none_when_no_data_available(monkeypatch):
    # Pipe open but no data ready (EOF-safe guard) → never blocks, returns None.
    _patch_stdin(monkeypatch, "later", has_data=False)
    assert stdin_util.read_stdin_if_available() is None


def test_resolve_cli_input_merges_prompt_first(monkeypatch):
    _patch_stdin(monkeypatch, "error log body")
    result = stdin_util.resolve_cli_input("Diagnose this")
    assert result == "Diagnose this\nerror log body"


def test_resolve_cli_input_stdin_only(monkeypatch):
    _patch_stdin(monkeypatch, "just the piped content")
    assert stdin_util.resolve_cli_input(None) == "just the piped content"


def test_resolve_cli_input_prompt_only_when_no_stdin(monkeypatch):
    _patch_stdin(monkeypatch, "ignored", isatty=True)
    assert stdin_util.resolve_cli_input("only prompt") == "only prompt"


def test_resolve_cli_input_none_when_nothing(monkeypatch):
    _patch_stdin(monkeypatch, "ignored", isatty=True)
    assert stdin_util.resolve_cli_input(None) is None


def test_resolve_cli_input_allow_stdin_false_skips_read(monkeypatch):
    # allow_stdin=False must never read stdin (interactive REPL entry points).
    def _boom(*a, **k):
        raise AssertionError("stdin must not be read when allow_stdin=False")

    monkeypatch.setattr(stdin_util, "read_stdin_if_available", _boom)
    assert stdin_util.resolve_cli_input("prompt", allow_stdin=False) == "prompt"


def test_legacy_delegates_to_shared_helper(monkeypatch):
    """The legacy read_stdin_if_available reuses the shared implementation."""
    try:
        from praisonai_code.cli.legacy.praison_ai import PraisonAI
    except ImportError as exc:
        pytest.skip(f"legacy module unavailable: {exc}")

    monkeypatch.setattr(
        stdin_util, "read_stdin_if_available", lambda: "shared result"
    )
    instance = PraisonAI.__new__(PraisonAI)
    assert instance.read_stdin_if_available() == "shared result"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
