"""Regression tests: `praisonai-mcp doctor` must not crash on legacy cp1252 consoles.

See https://github.com/MervinPraison/PraisonAI/issues/3213 — writing Unicode
status symbols (U+2713, U+2717, U+25CB) to a cp1252 console raised
UnicodeEncodeError. The doctor command must fall back to ASCII markers.
"""

from __future__ import annotations

import io

import pytest

from praisonai_mcp.mcp_server.cli import MCPServerCLI


class _Cp1252Stream(io.StringIO):
    """A StringIO that reports cp1252 encoding and rejects non-encodable text."""

    encoding = "cp1252"

    def write(self, text):  # type: ignore[override]
        text.encode("cp1252", errors="strict")
        return super().write(text)


class _Utf8Stream(io.StringIO):
    """A StringIO that reports utf-8 encoding."""

    encoding = "utf-8"


def test_supports_unicode_false_on_cp1252(monkeypatch):
    monkeypatch.setattr("sys.stdout", _Cp1252Stream())
    cli = MCPServerCLI()
    assert cli._supports_unicode() is False


def test_supports_unicode_true_on_utf8(monkeypatch):
    monkeypatch.setattr("sys.stdout", _Utf8Stream())
    cli = MCPServerCLI()
    assert cli._supports_unicode() is True


def test_doctor_no_crash_on_cp1252(monkeypatch):
    stream = _Cp1252Stream()
    monkeypatch.setattr("sys.stdout", stream)

    cli = MCPServerCLI()
    result = cli.cmd_doctor([])

    out = stream.getvalue()
    assert result in (cli.EXIT_SUCCESS, cli.EXIT_ERROR)
    assert "\u2713" not in out
    assert "\u2717" not in out
    assert "\u25cb" not in out
    assert "UnicodeEncodeError" not in out
    # ASCII markers are used instead of Unicode symbols. Which markers appear
    # depends on the environment (deps/keys), so accept any of the fallbacks.
    assert any(marker in out for marker in ("[OK]", "[--]", "[X]"))


def test_doctor_preserves_unicode_on_utf8(monkeypatch):
    stream = _Utf8Stream()
    monkeypatch.setattr("sys.stdout", stream)

    cli = MCPServerCLI()
    cli.cmd_doctor([])

    out = stream.getvalue()
    assert "\u2713" in out or "\u25cb" in out


def test_doctor_json_has_no_unicode_symbols(monkeypatch):
    import json

    stream = _Cp1252Stream()
    monkeypatch.setattr("sys.stdout", stream)

    cli = MCPServerCLI()
    result = cli.cmd_doctor(["--json"])

    out = stream.getvalue()
    assert result in (cli.EXIT_SUCCESS, cli.EXIT_ERROR)
    data = json.loads(out)
    assert "components" in data
    assert "environment" in data
    assert "dependencies" in data
    for symbol in ("\u2713", "\u2717", "\u25cb"):
        assert symbol not in out


def test_print_success_ascii_marker_is_literal(monkeypatch):
    """The ASCII fallback marker must render literally, not as Rich markup."""
    stream = _Cp1252Stream()
    monkeypatch.setattr("sys.stdout", stream)

    cli = MCPServerCLI()
    assert cli._supports_unicode() is False
    cli._print_success("ready to run")

    out = stream.getvalue()
    assert "[OK]" in out
    assert "ready to run" in out
    assert "UnicodeEncodeError" not in out


def test_doctor_json_emits_json_on_failure(monkeypatch):
    """A failure during --json must still produce valid JSON on stdout."""
    import json

    stream = _Utf8Stream()
    monkeypatch.setattr("sys.stdout", stream)

    def _boom():
        raise RuntimeError("register blew up")

    monkeypatch.setattr(
        "praisonai_mcp.mcp_server.adapters.register_all", _boom
    )

    cli = MCPServerCLI()
    result = cli.cmd_doctor(["--json"])

    out = stream.getvalue()
    assert result == cli.EXIT_ERROR
    data = json.loads(out)
    assert data["ready"] is False
    assert "error" in data
