"""A gateway's single-instance identity is its shared state, not its port (#6208)."""

import asyncio
import multiprocessing
import os
from pathlib import Path

import pytest

from praisonai_bot.gateway.port_utils import (
    format_collision_error,
    format_state_collision_error,
    resolve_state_dir,
    state_lock,
)


def _claim(d):
    import time
    time.sleep(0.2)  # line the workers up so the claims genuinely race
    return state_lock(Path(d)).acquire_lock("127.0.0.1", 8765)


def _seed_foreign_holder(lock, pid):
    lock.lock_file.write_text(f"{pid}\n127.0.0.1\n8765\n0\n\n")


def test_second_gateway_on_another_port_is_refused(tmp_path, monkeypatch):
    first = state_lock(tmp_path, port=8765)
    _seed_foreign_holder(first, os.getppid())  # a live process other than us
    second = state_lock(tmp_path, port=8766)
    assert second.lock_file == first.lock_file
    assert second.acquire_lock("127.0.0.1", 8766) is False
    msg = format_state_collision_error(tmp_path, second.get_lock_info())
    assert str(tmp_path) in msg and "HOME=" in msg and "PRAISONAI_HOME" not in msg


def test_distinct_state_dirs_are_independent(tmp_path):
    a = state_lock(tmp_path / "a")
    _seed_foreign_holder(a, os.getppid())
    assert state_lock(tmp_path / "b").acquire_lock("127.0.0.1", 8766) is True


def test_stale_state_lock_is_reclaimed(tmp_path, monkeypatch):
    lock = state_lock(tmp_path)
    _seed_foreign_holder(lock, 999999)
    monkeypatch.setattr(lock, "_is_process_running", lambda pid: False)
    assert lock.acquire_lock("127.0.0.1", 8765) is True


def test_state_dir_ignores_praisonai_home(tmp_path, monkeypatch):
    # The stores live under ~/.praisonai regardless of PRAISONAI_HOME, so a
    # different PRAISONAI_HOME must not escape the lock.
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    assert resolve_state_dir() == Path.home() / ".praisonai"


def test_concurrent_claims_have_exactly_one_winner(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(8) as pool:
        results = pool.map(_claim, [str(tmp_path)] * 8)
    assert sum(results) == 1


def test_claim_never_overwrites_existing_lock(tmp_path):
    lock = state_lock(tmp_path)
    _seed_foreign_holder(lock, os.getppid())
    assert lock.acquire_lock("127.0.0.1", 8766) is False
    assert lock.lock_file.read_text().startswith(str(os.getppid()))


def test_failed_startup_releases_both_locks(tmp_path, monkeypatch):
    from praisonai_bot.gateway import server as srv

    monkeypatch.setenv("HOME", str(tmp_path))  # isolate both lock files
    gw = srv.WebSocketGateway.__new__(srv.WebSocketGateway)
    gw._is_running, gw._host, gw._port = False, "127.0.0.1", 0
    gw._pid_lock = gw._state_lock = None

    async def boom():
        raise RuntimeError("bad config")

    gw._start_locked = boom
    monkeypatch.setattr("praisonai_bot.gateway.port_utils.check_port_available", lambda h, p: (True, None))
    with pytest.raises(RuntimeError, match="bad config"):
        asyncio.run(gw.start())
    assert gw._pid_lock is None and gw._state_lock is None
    assert not list((tmp_path / ".praisonai").glob("*.pid"))


def test_collision_error_no_longer_suggests_bare_port_change():
    msg = format_collision_error("127.0.0.1", 8765, {"pid": 1, "is_running": True})
    assert "Or use a different port" not in msg
    assert "HOME=" in msg and "PRAISONAI_HOME" not in msg
