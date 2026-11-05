"""Reclaiming a stale kanban claim closes the crashed run (Issue #6038)."""

import pytest

from praisonai_bot.kanban.sqlite_store import SQLiteKanbanStore

DEAD_PID = 2 ** 22 + 12345  # above pid_max on Linux, so never alive


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_KANBAN_DB", str(tmp_path / "kanban.db"))
    return SQLiteKanbanStore()


def _crash(store, task_id="k1"):
    """Claim + start a run whose worker died and whose lease has expired."""
    assert store.claim_task(task_id, "gateway_before", ttl_seconds=-1,
                            worker_pid=DEAD_PID)
    return store.start_run(task_id, profile="gateway_before")


def test_reclaim_closes_run_counts_failure_and_comments(store):
    store.create_task({"id": "k1", "title": "migrate db", "status": "ready",
                       "workspace_kind": "default"})
    run_id = _crash(store)

    assert store.reclaim_stale_claims() == ["k1"]

    run = next(r for r in store.get_runs("k1") if r.id == run_id)
    assert run.outcome == "crashed"
    assert run.ended_at
    assert "interrupted" in run.error
    task = store.get_task("k1")
    assert task.status == "ready"
    assert task.consecutive_failures == 1
    assert any(c.text.startswith("interrupted:") for c in store.get_comments("k1"))
    assert store.get_retry_context("k1")[0]["outcome"] == "crashed"


def test_crash_loop_trips_circuit_breaker(store):
    store.create_task({"id": "k2", "title": "loop", "status": "ready",
                       "workspace_kind": "default", "max_retries": 2})
    for _ in range(2):
        _crash(store, "k2")
        store.reclaim_stale_claims()
    assert store.get_task("k2").status == "blocked"


def test_reclaim_bookkeeping_commits_with_the_reclaim(store, monkeypatch):
    """No window where the task is 'ready' but the old attempt is unaccounted."""
    store.create_task({"id": "k3", "title": "atomic", "status": "ready",
                       "workspace_kind": "default", "max_retries": 1})
    run_id = _crash(store, "k3")
    seen = []
    emit = store._emit_hook

    def _spy(event, task_id, **payload):
        if event == "kanban_task_moved":
            run = next(r for r in store.get_runs(task_id) if r.id == run_id)
            seen.append((run.outcome, store.get_task(task_id).status))
        return emit(event, task_id, **payload)

    monkeypatch.setattr(store, "_emit_hook", _spy)
    assert store.reclaim_stale_claims() == ["k3"]
    # At the first post-commit announcement the run is already closed and the
    # circuit breaker already tripped, so no dispatcher could claim it as ready.
    assert seen == [("crashed", "blocked")]
