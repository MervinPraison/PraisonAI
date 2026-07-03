"""Unit tests for the wrapper-side code-skew guard (Issue #2460).

Covers the concrete ``read_code_fingerprint`` helper, the startup
``capture_boot_fingerprint`` baseline, and the ``check_code_skew`` pre-flight
guard consulted by the ``/model`` command handler.
"""

import os

from praisonai_bot.bots._commands import (
    capture_boot_fingerprint,
    check_code_skew,
    read_code_fingerprint,
    _fingerprint_dir,
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


def test_read_code_fingerprint_default_spans_both_packages():
    # With no explicit directory, the fingerprint must cover BOTH the wrapper
    # (praisonai) and the lazily-imported SDK (praisonaiagents) so an in-place
    # update to either is detected. (Greptile P1)
    fp = read_code_fingerprint()
    assert isinstance(fp, str) and fp
    assert "praisonai=" in fp
    assert "praisonaiagents=" in fp


def test_read_code_fingerprint_default_changes_when_sdk_changes(monkeypatch):
    # If the praisonaiagents portion changes while praisonai stays the same,
    # the combined fingerprint must change — catching an SDK-only update.
    import praisonai_bot.bots._commands as commands

    def fake_fp(directory):
        if directory and directory.endswith("praisonaiagents"):
            return "sdk-rev-1"
        return "wrapper-rev"

    monkeypatch.setattr(commands, "_fingerprint_dir", fake_fp)

    # Force the praisonaiagents path to end with the package name so the stub
    # can distinguish it deterministically regardless of install layout.
    import praisonaiagents

    monkeypatch.setattr(
        praisonaiagents, "__file__", "/x/praisonaiagents/__init__.py", raising=False
    )

    before = read_code_fingerprint()

    def fake_fp_changed(directory):
        if directory and directory.endswith("praisonaiagents"):
            return "sdk-rev-2"
        return "wrapper-rev"

    monkeypatch.setattr(commands, "_fingerprint_dir", fake_fp_changed)
    after = read_code_fingerprint()

    assert before != after
    assert "praisonaiagents=sdk-rev-1" in before
    assert "praisonaiagents=sdk-rev-2" in after


def test_fingerprint_dir_explicit_dir_is_single(tmp_path):
    # An explicit directory fingerprints only that directory (no package span).
    py_file = tmp_path / "module.py"
    py_file.write_text("x = 1\n")
    os.utime(py_file, (1_700_000_000, 1_700_000_000))
    assert _fingerprint_dir(str(tmp_path)) == "mtime:1700000000000000000"


def test_fingerprint_dir_combines_git_rev_with_mtime(tmp_path, monkeypatch):
    # When git succeeds, the newest .py mtime is combined with the rev so an
    # in-place file overwrite that does NOT advance HEAD still moves the
    # fingerprint (Greptile P1: dirty/source checkouts).
    import subprocess

    class _Result:
        returncode = 0
        stdout = "a" * 40 + "\n"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Result())

    py_file = tmp_path / "module.py"
    py_file.write_text("x = 1\n")
    os.utime(py_file, (1_700_000_000, 1_700_000_000))

    fp = _fingerprint_dir(str(tmp_path))
    assert fp == "a" * 40 + "+mtime:1700000000000000000"


def test_fingerprint_dir_dirty_overwrite_changes_fingerprint(tmp_path, monkeypatch):
    # Same HEAD, but a .py file is overwritten with a newer mtime -> the
    # combined fingerprint must change so the guard catches the skew.
    import subprocess

    class _Result:
        returncode = 0
        stdout = "deadbeef" * 5 + "\n"  # 40 hex chars

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Result())

    py_file = tmp_path / "module.py"
    py_file.write_text("x = 1\n")
    os.utime(py_file, (1_700_000_000, 1_700_000_000))
    before = _fingerprint_dir(str(tmp_path))

    os.utime(py_file, (1_700_000_005, 1_700_000_005))
    after = _fingerprint_dir(str(tmp_path))

    assert before != after


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
    import praisonai_bot.bots._commands as commands

    sm = _FakeSessionManager()
    sm._boot_code_fp = "samefp"
    monkeypatch.setattr(commands, "read_code_fingerprint", lambda *a, **k: "samefp")
    assert check_code_skew(sm) is None


def test_check_code_skew_reports_skew(monkeypatch):
    import praisonai_bot.bots._commands as commands

    sm = _FakeSessionManager()
    sm._boot_code_fp = "a" * 40
    monkeypatch.setattr(commands, "read_code_fingerprint", lambda *a, **k: "b" * 40)
    msg = check_code_skew(sm)
    assert msg is not None
    assert "Restart the gateway" in msg
    assert "aaaaaaa" in msg and "bbbbbbb" in msg


def test_check_code_skew_first_call_captures_baseline(monkeypatch):
    import praisonai_bot.bots._commands as commands

    sm = _FakeSessionManager()
    monkeypatch.setattr(commands, "read_code_fingerprint", lambda *a, **k: "boot-fp")
    # No baseline yet -> capture and return None (fail-open first call).
    assert check_code_skew(sm) is None
    assert sm._boot_code_fp == "boot-fp"


def test_check_code_skew_opt_out_returns_none(monkeypatch):
    import praisonai_bot.bots._commands as commands

    sm = _FakeSessionManager()
    sm._boot_code_fp = "a" * 40
    sm.code_skew_guard = False
    monkeypatch.setattr(commands, "read_code_fingerprint", lambda *a, **k: "b" * 40)
    assert check_code_skew(sm) is None


def test_check_code_skew_none_session_manager():
    assert check_code_skew(None) is None


def test_capture_boot_fingerprint_caches_detect_predicate():
    # The pure comparison predicate must be resolved at boot (while imports are
    # known-good) and cached, so the guard never re-imports the SDK gateway
    # surface during a hot operation (Greptile P1: "Guard imports too late").
    from praisonaiagents.gateway import detect_code_skew as real_predicate

    sm = _FakeSessionManager()
    capture_boot_fingerprint(sm)
    assert getattr(sm, "_boot_detect_code_skew", None) is real_predicate


def test_check_code_skew_uses_cached_predicate_not_fresh_import(monkeypatch):
    # If a cached boot predicate exists, the guard must use it and must NOT rely
    # on a fresh import of the SDK gateway (which could fail after an in-place
    # update). Simulate a broken import surface to prove independence.
    import praisonai_bot.bots._commands as commands

    sm = _FakeSessionManager()
    sm._boot_code_fp = "a" * 40
    sm._boot_detect_code_skew = lambda boot, disk: ("aaaaaaa", "bbbbbbb")
    monkeypatch.setattr(commands, "read_code_fingerprint", lambda *a, **k: "b" * 40)

    # Break the SDK gateway import path; the cached predicate must still work.
    import praisonaiagents.gateway as gw

    monkeypatch.delattr(gw, "detect_code_skew", raising=False)

    msg = check_code_skew(sm)
    assert msg is not None
    assert "Restart the gateway" in msg
