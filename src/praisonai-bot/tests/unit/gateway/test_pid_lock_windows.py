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

from praisonai_bot.gateway.port_utils import GatewayPIDLock


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
