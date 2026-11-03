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


def _claim(d, start, done, results):
    start.wait()  # release every worker at once so the claims genuinely race
    results.put(state_lock(Path(d)).acquire_lock("127.0.0.1", 8765))
    done.wait()  # stay alive until all claimed, so no lock is seen as stale


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
    n = 8
    start, done, results = ctx.Barrier(n), ctx.Barrier(n), ctx.Queue()
    procs = [ctx.Process(target=_claim, args=(str(tmp_path), start, done, results)) for _ in range(n)]
    for p in procs:
        p.start()
    outcomes = [results.get(timeout=60) for _ in range(n)]
    for p in procs:
        p.join(timeout=60)
    assert sum(outcomes) == 1


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


def test_start_failure_keeps_state_lock_owned_by_start_with_config(tmp_path, monkeypatch):
    # start_with_config claims the state lock before channels start; if start()
    # then fails, channels are still polling, so start() must not drop it.
    from praisonai_bot.gateway import server as srv

    monkeypatch.setenv("HOME", str(tmp_path))
    gw = srv.WebSocketGateway.__new__(srv.WebSocketGateway)
    gw._is_running, gw._host, gw._port = False, "127.0.0.1", 0
    gw._pid_lock = gw._state_lock = None
    gw._acquire_state_lock()
    held = gw._state_lock

    async def boom():
        raise RuntimeError("bind error")

    gw._start_locked = boom
    monkeypatch.setattr("praisonai_bot.gateway.port_utils.check_port_available", lambda h, p: (True, None))
    with pytest.raises(RuntimeError, match="bind error"):
        asyncio.run(gw.start())
    assert gw._pid_lock is None
    assert gw._state_lock is held and held.lock_file.exists()
    gw._release_locks()  # start_with_config's finally, after channels stop
    assert gw._state_lock is None and not held.lock_file.exists()


def test_collision_error_no_longer_suggests_bare_port_change():
    msg = format_collision_error("127.0.0.1", 8765, {"pid": 1, "is_running": True})
    assert "Or use a different port" not in msg
    assert "HOME=" in msg and "PRAISONAI_HOME" not in msg
