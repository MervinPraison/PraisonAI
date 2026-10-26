"""Regression tests for #6025: the dispatcher heartbeats its own children.

A healthy worker that outlives the claim lease + stale timeout must not be
reclaimed and re-dispatched while it is still running.
"""

import asyncio
import subprocess
import sys

import pytest

from praisonai_bot.gateway.kanban_dispatcher import KanbanDispatcher
from praisonai_bot.kanban.sqlite_store import SQLiteKanbanStore

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="uses sleep stub")


class _StubDispatcher(KanbanDispatcher):
    def __init__(self, store, seconds, **kwargs):
        super().__init__(**kwargs)
        self._store = store
        self._seconds = seconds

    def _get_kanban_store(self):
        return self._store

    def _build_execution_command(self, task):
        return [sys.executable, "-c", f"import time; time.sleep({self._seconds})"]


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_KANBAN_DB", str(tmp_path / "kanban.db"))
    return SQLiteKanbanStore()


def _run(coro):
    return asyncio.run(coro)


def test_long_running_worker_is_not_reclaimed(store):
    store.create_task({"id": "t1", "title": "long job", "status": "ready",
                       "workspace_kind": "default"})
    d = _StubDispatcher(store, 5, max_concurrent=3, poll_interval=0.5,
                        claim_ttl_seconds=1, stale_timeout_seconds=2)

    async def drive():
        handles = []
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        while loop.time() - t0 < 4.5:
            await d.dispatch_once()
            proc = d.running_tasks.get("t1")
            if proc is not None and proc not in handles:
                handles.append(proc)
            await asyncio.sleep(0.25)
        return handles

    handles = _run(drive())
    try:
        assert len(handles) == 1
        runs = store.get_runs("t1")
        assert len(runs) == 1
        assert runs[0].ended_at is None
        assert not [e for e in store.list_events()
                    if e.task_id == "t1" and e.event_type == "reclaimed"]

        handles[0].wait(timeout=10)
        _run(d.dispatch_once())
        runs = store.get_runs("t1")
        assert len(runs) == 1
        assert runs[0].outcome == "completed"
        assert store.get_task("t1").status == "done"
    finally:
        for p in handles:
            if p.poll() is None:
                p.kill()


def test_lost_claim_terminates_child(store):
    store.create_task({"id": "t2", "title": "job", "status": "ready",
                       "workspace_kind": "default"})
    d = _StubDispatcher(store, 30, max_concurrent=1, poll_interval=0.5)
    _run(d.dispatch_once())
    proc = d.running_tasks["t2"]
    try:
        store.release_claim("t2", d.worker_id)  # operator takes the card back
        d._heartbeat_children(store)
        assert "t2" not in d.running_tasks
        assert proc.wait(timeout=10) is not None
        runs = store.get_runs("t2")
        assert len(runs) == 1 and runs[0].outcome == "failed"
    finally:
        if proc.poll() is None:
            proc.kill()


def test_reclaim_of_dead_worker_closes_run_and_counts_failure(store):
    store.create_task({"id": "t3", "title": "job", "status": "ready",
                       "workspace_kind": "default"})
    # Simulate another dispatcher whose worker has died.
    assert store.claim_task("t3", "other", ttl_seconds=0, worker_pid=0)
    run_id = store.start_run("t3", profile="other")
    d = KanbanDispatcher(claim_ttl_seconds=1, stale_timeout_seconds=1)

    d._reclaim_stale_claims(store)

    run = [r for r in store.get_runs("t3") if r.id == run_id][0]
    assert run.outcome == "crashed"
    assert run.ended_at
    assert store.get_task("t3").consecutive_failures == 1


def test_live_handle_is_never_overwritten(store):
    store.create_task({"id": "t4", "title": "job", "status": "ready",
                       "workspace_kind": "default"})
    d = _StubDispatcher(store, 30, max_concurrent=2)
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    d.running_tasks["t4"] = proc
    d._heartbeat_children = lambda _store: None  # isolate the spawn guard
    try:
        assert _run(d.dispatch_once()) == 0
        assert d.running_tasks["t4"] is proc
    finally:
        proc.kill()
        proc.wait()
