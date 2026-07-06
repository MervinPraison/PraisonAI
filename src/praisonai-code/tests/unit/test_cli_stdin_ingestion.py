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
    # Drive the platform-agnostic data-available check deterministically instead
    # of relying on the real select()/stat() so tests behave identically on
    # every OS (Unix uses select, Windows uses a stat-based pipe check).
    monkeypatch.setattr(stdin_util, "_stdin_has_data", lambda: has_data)
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


def test_read_stdin_reads_piped_content_on_windows(monkeypatch):
    # Windows can't use select() for pipes, but a stat-based pipe check lets us
    # read redirected/piped stdin without blocking (issue #2702).
    _patch_stdin(monkeypatch, "piped data")
    monkeypatch.setattr(stdin_util.sys, "platform", "win32")
    assert stdin_util.read_stdin_if_available() == "piped data"


def test_stdin_has_data_windows_uses_pipe_check(monkeypatch):
    # On Windows, _stdin_has_data() must defer to the stat-based pipe check
    # rather than select() (which is socket-only there).
    monkeypatch.setattr(stdin_util.sys, "platform", "win32")
    monkeypatch.setattr(stdin_util, "_windows_stdin_is_pipe", lambda: True)
    assert stdin_util._stdin_has_data() is True

    monkeypatch.setattr(stdin_util, "_windows_stdin_is_pipe", lambda: False)
    assert stdin_util._stdin_has_data() is False


def test_windows_stdin_is_pipe_detects_fifo(monkeypatch):
    # A FIFO/pipe or regular-file redirection carries piped data on Windows.
    import stat as _stat

    class _FakeStat:
        st_mode = _stat.S_IFIFO

    class _HandleStdin:
        def fileno(self):
            return 0

    monkeypatch.setattr(stdin_util.sys, "stdin", _HandleStdin())
    monkeypatch.setattr(stdin_util.os, "fstat", lambda fd: _FakeStat())
    assert stdin_util._windows_stdin_is_pipe() is True


def test_read_stdin_respects_size_cap(monkeypatch):
    # Read is bounded by _MAX_STDIN_BYTES so a huge pipe can't buffer unbounded.
    fake = _patch_stdin(monkeypatch, "x" * (stdin_util._MAX_STDIN_BYTES + 100))
    result = stdin_util.read_stdin_if_available()
    assert result is not None
    assert len(result) <= stdin_util._MAX_STDIN_BYTES


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
