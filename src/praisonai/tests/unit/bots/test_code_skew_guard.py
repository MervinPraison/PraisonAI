"""Unit tests for the wrapper-side code-skew guard (Issue #2460).

Covers the concrete ``read_code_fingerprint`` helper, the startup
``capture_boot_fingerprint`` baseline, and the ``check_code_skew`` pre-flight
guard consulted by the ``/model`` command handler.
"""

import os

from praisonai.bots._commands import (
    capture_boot_fingerprint,
    check_code_skew,
    read_code_fingerprint,
)


class _FakeSessionManager:
    """Minimal stand-in carrying just the attributes the guard touches."""


def test_read_code_fingerprint_returns_string_for_real_package():
    # The running wrapper package directory exists, so a fingerprint
    # (git rev or mtime) must be derivable.
    fp = read_code_fingerprint()
    assert isinstance(fp, str)
    assert fp


def test_read_code_fingerprint_fails_open_on_bad_dir():
    fp = read_code_fingerprint("/nonexistent/path/that/should/not/exist")
    # Git fails and there are no .py files to scan -> None.
    assert fp is None


def test_read_code_fingerprint_mtime_fallback(tmp_path):
    # A plain directory (not a git checkout) falls back to a nanosecond mtime
    # fingerprint when it contains .py files.
    py_file = tmp_path / "module.py"
    py_file.write_text("x = 1\n")
    os.utime(py_file, (1_700_000_000, 1_700_000_000))
    fp = read_code_fingerprint(str(tmp_path))
    assert fp == "mtime:1700000000000000000"


def test_read_code_fingerprint_ignores_non_python_files(tmp_path):
    (tmp_path / "data.txt").write_text("not python\n")
    fp = read_code_fingerprint(str(tmp_path))
    assert fp is None


def test_capture_boot_fingerprint_caches_on_session_manager():
    sm = _FakeSessionManager()
    fp = capture_boot_fingerprint(sm)
    assert fp == getattr(sm, "_boot_code_fp")


def test_capture_boot_fingerprint_is_idempotent():
    sm = _FakeSessionManager()
    sm._boot_code_fp = "existing-fp"
    assert capture_boot_fingerprint(sm) == "existing-fp"
    assert sm._boot_code_fp == "existing-fp"


def test_capture_boot_fingerprint_fails_open_on_none():
    assert capture_boot_fingerprint(None) is None


def test_check_code_skew_no_message_when_unchanged(monkeypatch):
    import praisonai.bots._commands as commands

    sm = _FakeSessionManager()
    sm._boot_code_fp = "samefp"
    monkeypatch.setattr(commands, "read_code_fingerprint", lambda *a, **k: "samefp")
    assert check_code_skew(sm) is None


def test_check_code_skew_reports_skew(monkeypatch):
    import praisonai.bots._commands as commands

    sm = _FakeSessionManager()
    sm._boot_code_fp = "a" * 40
    monkeypatch.setattr(commands, "read_code_fingerprint", lambda *a, **k: "b" * 40)
    msg = check_code_skew(sm)
    assert msg is not None
    assert "Restart the gateway" in msg
    assert "aaaaaaa" in msg and "bbbbbbb" in msg


def test_check_code_skew_first_call_captures_baseline(monkeypatch):
    import praisonai.bots._commands as commands

    sm = _FakeSessionManager()
    monkeypatch.setattr(commands, "read_code_fingerprint", lambda *a, **k: "boot-fp")
    # No baseline yet -> capture and return None (fail-open first call).
    assert check_code_skew(sm) is None
    assert sm._boot_code_fp == "boot-fp"


def test_check_code_skew_opt_out_returns_none(monkeypatch):
    import praisonai.bots._commands as commands

    sm = _FakeSessionManager()
    sm._boot_code_fp = "a" * 40
    sm.code_skew_guard = False
    monkeypatch.setattr(commands, "read_code_fingerprint", lambda *a, **k: "b" * 40)
    assert check_code_skew(sm) is None


def test_check_code_skew_none_session_manager():
    assert check_code_skew(None) is None
