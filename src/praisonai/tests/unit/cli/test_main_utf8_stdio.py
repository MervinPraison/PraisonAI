"""Regression tests for #5855: Typer CLI must not crash on cp1252 stdout."""

import io
import sys

from praisonai.__main__ import _ensure_utf8_stdio


def _stream(encoding):
    return io.TextIOWrapper(io.BytesIO(), encoding=encoding)


def test_cp1252_stdout_reconfigured_to_utf8(monkeypatch):
    out, err = _stream("cp1252"), _stream("cp1252")
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)

    _ensure_utf8_stdio()

    assert out.encoding == "utf-8" and err.encoding == "utf-8"
    out.write("✓ ✗ ⚠ ─│┌")  # must not raise
    out.flush()


def test_utf8_stdout_left_untouched(monkeypatch):
    out = _stream("utf-8")
    calls = []
    monkeypatch.setattr(out, "reconfigure", lambda **kw: calls.append(kw), raising=False)
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", out)

    _ensure_utf8_stdio()

    assert calls == []


def test_stream_without_reconfigure_is_ignored(monkeypatch):
    class Legacy:
        encoding = "cp1252"

    monkeypatch.setattr(sys, "stdout", Legacy())
    monkeypatch.setattr(sys, "stderr", Legacy())

    _ensure_utf8_stdio()  # must not raise
