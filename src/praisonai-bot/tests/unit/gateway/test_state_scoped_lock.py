"""A gateway's single-instance identity is its shared state, not its port (#6208)."""

import os

from praisonai_bot.gateway.port_utils import (
    format_collision_error,
    format_state_collision_error,
    resolve_state_dir,
    state_lock,
)


def _seed_foreign_holder(lock, pid):
    lock.lock_file.write_text(f"{pid}\n127.0.0.1\n8765\n0\n\n")


def test_second_gateway_on_another_port_is_refused(tmp_path, monkeypatch):
    first = state_lock(tmp_path, port=8765)
    _seed_foreign_holder(first, os.getppid())  # a live process other than us
    second = state_lock(tmp_path, port=8766)
    assert second.lock_file == first.lock_file
    assert second.acquire_lock("127.0.0.1", 8766) is False
    msg = format_state_collision_error(tmp_path, second.get_lock_info())
    assert str(tmp_path) in msg and "PRAISONAI_HOME" in msg


def test_distinct_state_dirs_are_independent(tmp_path):
    a = state_lock(tmp_path / "a")
    _seed_foreign_holder(a, os.getppid())
    assert state_lock(tmp_path / "b").acquire_lock("127.0.0.1", 8766) is True


def test_stale_state_lock_is_reclaimed(tmp_path, monkeypatch):
    lock = state_lock(tmp_path)
    _seed_foreign_holder(lock, 999999)
    monkeypatch.setattr(lock, "_is_process_running", lambda pid: False)
    assert lock.acquire_lock("127.0.0.1", 8765) is True


def test_resolve_state_dir_honours_praisonai_home(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    assert resolve_state_dir() == tmp_path


def test_collision_error_no_longer_suggests_bare_port_change():
    msg = format_collision_error("127.0.0.1", 8765, {"pid": 1, "is_running": True})
    assert "Or use a different port" not in msg
    assert "PRAISONAI_HOME" in msg
