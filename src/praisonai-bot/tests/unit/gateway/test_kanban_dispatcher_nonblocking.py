"""The kanban dispatcher must not run blocking git work on the event loop."""

import asyncio
import itertools
import os
import subprocess
import sys
import threading
import time
import types

import pytest

import praisonai_bot.gateway.kanban_dispatcher as kd
from praisonai_bot.kanban.sqlite_store import SQLiteKanbanStore

GIT_DELAY = 0.5


class _Stub(kd.KanbanDispatcher):
    def _build_execution_command(self, task):
        return ["true"]


async def _heartbeat(gaps, stop):
    last = time.monotonic()
    while not stop.is_set():
        await asyncio.sleep(0.05)
        now = time.monotonic()
        gaps.append(now - last)
        last = now


@pytest.fixture
def slow_git(tmp_path, monkeypatch):
    """Patch ``run_guarded`` with a synchronous sleep, recording overlap."""
    monkeypatch.setenv("PRAISONAI_KANBAN_DB", str(tmp_path / "kanban.db"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    state = {"active": 0, "max_active": 0, "calls": []}
    lock = threading.Lock()

    def fake(cmd, *, timeout=None, cwd=None, **kw):
        with lock:
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
            state["calls"].append(" ".join(cmd[:3]))
        try:
            time.sleep(GIT_DELAY)
            if list(cmd[1:3]) == ["worktree", "add"]:
                os.makedirs(cmd[3], exist_ok=True)
            out = {"rev-parse": "main\n", "rev-list": "0\n"}.get(cmd[1], "")
            return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
        finally:
            with lock:
                state["active"] -= 1

    monkeypatch.setattr(kd, "run_guarded", fake)
    return state


@pytest.mark.skipif(sys.platform == "win32", reason="uses the POSIX `true` worker")
async def test_dispatch_does_not_block_event_loop(slow_git):
    store = SQLiteKanbanStore()
    store.create_task({"id": "w1", "title": "isolated", "status": "ready",
                       "workspace_kind": "worktree"})
    d = _Stub(max_concurrent=1)
    gaps, stop = [], asyncio.Event()
    hb = asyncio.create_task(_heartbeat(gaps, stop))
    await asyncio.sleep(0.1)

    assert await d.dispatch_once() == 1          # spawn: rev-parse + worktree add
    await asyncio.to_thread(d.running_tasks["w1"].wait)
    await d.dispatch_once()                      # completion: commit/merge/cleanup
    await asyncio.sleep(0.1)
    stop.set()
    await hb

    assert "git worktree add" in slow_git["calls"]
    assert "git merge --no-ff" in slow_git["calls"]
    assert max(gaps) < 0.3, f"event loop stalled for {max(gaps):.2f}s"


async def test_blocking_work_is_serialised(slow_git):
    a, b = _Stub(), _Stub()
    await asyncio.gather(
        a._run_blocking(a._run_git, "status"),
        b._run_blocking(b._run_git, "status"),
    )
    assert slow_git["max_active"] == 1


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")
async def test_shutdown_terminates_worker_descendants(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_KANBAN_DB", str(tmp_path / "kanban.db"))
    pid_file = tmp_path / "grandchild.pid"

    class _Spawner(kd.KanbanDispatcher):
        def _build_execution_command(self, task):
            # Worker that starts a long-lived grandchild and waits on it.
            return ["sh", "-c", f"sleep 60 & echo $! > {pid_file}; wait"]

    class _Task:
        id, board, title, body = "t1", "default", "t1", ""

    d = _Spawner()
    assert await d._spawn_worker(_Task(), store=None)
    for _ in range(100):
        if pid_file.exists() and pid_file.read_text().strip():
            break
        await asyncio.sleep(0.05)
    grandchild = int(pid_file.read_text())

    # Skip the 30 s graceful window; go straight to force-terminate.
    ticks = itertools.count(step=1000)
    monkeypatch.setattr(kd, "time", types.SimpleNamespace(time=lambda: next(ticks)))
    await d._shutdown()

    for _ in range(50):
        try:
            os.kill(grandchild, 0)
        except ProcessLookupError:
            break
        await asyncio.sleep(0.05)
    else:
        os.kill(grandchild, 9)
        pytest.fail("worker's grandchild survived shutdown")
