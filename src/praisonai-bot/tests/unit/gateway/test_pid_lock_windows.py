#!/usr/bin/env python3
"""Regression tests for PID lock process checks on Windows.

On Windows, ``os.kill(pid, 0)`` can raise ``SystemError`` ("returned a result
with an exception set") which previously propagated through ``gateway status``.
"""

import os
import sys
from pathlib import Path

# Resolve from the repository root so direct execution finds the packages.
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai-bot"))

from praisonai_bot.gateway.port_utils import (
    GatewayPIDLock,
    _process_create_time,
    check_port_available,
)


def _make_lock(tmp_path):
    return GatewayPIDLock(lock_dir=tmp_path, host="127.0.0.1", port=18789)


def test_is_process_running_systemerror(monkeypatch, tmp_path):
    """SystemError from os.kill must be treated as 'not running', not raised."""
    def bad_kill(pid, sig):
        raise SystemError("kill returned a result with an exception set")

    monkeypatch.setattr(os, "kill", bad_kill)
    assert _make_lock(tmp_path)._is_process_running(12345) is False


def test_is_process_running_valueerror(monkeypatch, tmp_path):
    """ValueError from os.kill must be treated as 'not running', not raised."""
    def bad_kill(pid, sig):
        raise ValueError("invalid pid")

    monkeypatch.setattr(os, "kill", bad_kill)
    assert _make_lock(tmp_path)._is_process_running(-1) is False


def test_is_process_running_dead_process(monkeypatch, tmp_path):
    """OSError still maps to 'not running' so stale locks are detected."""
    def dead_kill(pid, sig):
        raise ProcessLookupError()

    monkeypatch.setattr(os, "kill", dead_kill)
    assert _make_lock(tmp_path)._is_process_running(99999) is False


def test_is_process_running_alive(monkeypatch, tmp_path):
    """A successful os.kill(pid, 0) reports the process as running."""
    monkeypatch.setattr(os, "kill", lambda pid, sig: None)
    assert _make_lock(tmp_path)._is_process_running(4321) is True


def test_a_process_we_may_not_signal_is_treated_as_running(monkeypatch, tmp_path):
    """PermissionError means the process exists. Reporting it dead deletes a
    live gateway's lock and admits a second poller for the same bot token."""
    def denied_kill(pid, sig):
        raise PermissionError()

    monkeypatch.setattr(os, "kill", denied_kill)
    assert _make_lock(tmp_path)._is_process_running(1) is True


def test_a_recycled_pid_is_not_mistaken_for_the_gateway(tmp_path):
    """Same PID, wrong start-time fingerprint: the original gateway is gone."""
    lock = _make_lock(tmp_path)
    assert lock.acquire_lock("127.0.0.1", 18789) is True

    # Rewrite the lock keeping our PID but with a start time that cannot match.
    content = lock.lock_file.read_text().strip().split("\n")
    content[0] = str(os.getpid())
    content[4] = "0.0"  # wrong create_time
    lock.lock_file.write_text("\n".join(content) + "\n")

    assert lock._lock_is_ours() is False


def test_matching_fingerprint_keeps_the_lock_ours(tmp_path):
    """Our own live process with the recorded fingerprint stays 'ours'."""
    lock = _make_lock(tmp_path)
    assert lock.acquire_lock("127.0.0.1", 18789) is True
    assert lock._lock_is_ours() is True


def test_port_collision_message_survives_the_installed_psutil():
    """check_port_available must never raise on the installed psutil; a busy
    port returns (False, ...) so the friendly diagnostic can render."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        busy_port = srv.getsockname()[1]
        ok, _pid = check_port_available("127.0.0.1", busy_port)
        assert ok is False


def test_create_time_helper_returns_float_for_live_process():
    """The fingerprint helper works against the current process."""
    assert isinstance(_process_create_time(os.getpid()), float)
