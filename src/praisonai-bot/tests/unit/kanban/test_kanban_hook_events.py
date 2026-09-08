"""Kanban lifecycle hook events must actually fire on real state transitions.

``praisonaiagents.hooks.HookEvent`` declares KANBAN_TASK_CREATED / _CLAIMED /
_MOVED / _DONE / _BLOCKED / _FAILED. A plugin author registers a callback on
one of them and expects it to fire when the board changes. These tests drive a
real ``SQLiteKanbanStore`` through each transition and assert the hook is
delivered.
"""

import pytest

from praisonaiagents.hooks.registry import (
    HookRegistry,
    add_hook,
    get_default_registry,
    set_default_registry,
)
from praisonaiagents.hooks.types import HookEvent, HookResult

from praisonai_bot.kanban.sqlite_store import SQLiteKanbanStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_KANBAN_DB", str(tmp_path / "kanban.db"))
    return SQLiteKanbanStore()


@pytest.fixture
def record():
    """Fresh default registry + a recorder factory for one or more events."""
    previous = get_default_registry()
    set_default_registry(HookRegistry())
    seen = {}

    def _record(*events):
        for event in events:
            bucket = seen.setdefault(event, [])
            add_hook(
                event,
                lambda data, _b=bucket: _b.append(data.to_dict()) or HookResult.allow(),
            )
        return seen

    try:
        yield _record
    finally:
        set_default_registry(previous)


def test_created_event_fires_on_create_task(store, record):
    seen = record(HookEvent.KANBAN_TASK_CREATED)
    task = store.create_task({"title": "write the docs"})

    fired = seen[HookEvent.KANBAN_TASK_CREATED]
    assert len(fired) == 1, "KANBAN_TASK_CREATED never fired for store.create_task()"
    assert fired[0]["task_id"] == task.id
    assert fired[0]["event_name"] == "kanban_task_created"
    assert fired[0]["status"] == "todo"


def test_created_event_does_not_refire_for_an_idempotent_create(store, record):
    seen = record(HookEvent.KANBAN_TASK_CREATED)
    store.create_task({"title": "once"}, idempotency_key="k1")
    store.create_task({"title": "once"}, idempotency_key="k1")

    assert len(seen[HookEvent.KANBAN_TASK_CREATED]) == 1


def test_claimed_event_fires_on_successful_claim(store, record):
    task = store.create_task({"title": "claim me", "status": "ready"})
    seen = record(HookEvent.KANBAN_TASK_CLAIMED)

    assert store.claim_task(task.id, "worker-1") is True
    fired = seen[HookEvent.KANBAN_TASK_CLAIMED]
    assert len(fired) == 1, "KANBAN_TASK_CLAIMED never fired for store.claim_task()"
    assert fired[0]["task_id"] == task.id
    assert fired[0]["assignee"] == "worker-1"
    assert fired[0]["to_status"] == "running"


def test_claimed_event_does_not_fire_when_the_claim_is_lost(store, record):
    task = store.create_task({"title": "contended", "status": "ready"})
    store.claim_task(task.id, "worker-1")
    seen = record(HookEvent.KANBAN_TASK_CLAIMED)

    assert store.claim_task(task.id, "worker-2") is False
    assert seen[HookEvent.KANBAN_TASK_CLAIMED] == []


def test_moved_event_fires_on_move_task(store, record):
    task = store.create_task({"title": "move me"})
    seen = record(HookEvent.KANBAN_TASK_MOVED)

    store.move_task(task.id, "ready")
    fired = seen[HookEvent.KANBAN_TASK_MOVED]
    assert len(fired) == 1, "KANBAN_TASK_MOVED never fired for store.move_task()"
    assert fired[0]["from_status"] == "todo"
    assert fired[0]["to_status"] == "ready"


def test_done_event_fires_when_a_task_moves_to_done(store, record):
    task = store.create_task({"title": "finish me"})
    seen = record(HookEvent.KANBAN_TASK_DONE, HookEvent.KANBAN_TASK_MOVED)

    store.move_task(task.id, "done")
    done = seen[HookEvent.KANBAN_TASK_DONE]
    assert len(done) == 1, "KANBAN_TASK_DONE never fired for a task moved to 'done'"
    assert done[0]["task_id"] == task.id
    assert done[0]["status"] == "done"
    # The generic move event still fires exactly once alongside it.
    assert len(seen[HookEvent.KANBAN_TASK_MOVED]) == 1


def test_blocked_event_fires_when_a_task_moves_to_blocked(store, record):
    task = store.create_task({"title": "stuck"})
    seen = record(HookEvent.KANBAN_TASK_BLOCKED)

    store.move_task(task.id, "blocked")
    fired = seen[HookEvent.KANBAN_TASK_BLOCKED]
    assert len(fired) == 1, "KANBAN_TASK_BLOCKED never fired for a task moved to 'blocked'"
    assert fired[0]["task_id"] == task.id
    assert fired[0]["status"] == "blocked"


def test_failed_event_fires_when_an_attempt_is_recorded_as_failed(store, record):
    task = store.create_task({"title": "flaky", "max_retries": 3})
    seen = record(HookEvent.KANBAN_TASK_FAILED)

    assert store.record_failure(task.id, error="exit code 1") is False
    fired = seen[HookEvent.KANBAN_TASK_FAILED]
    assert len(fired) == 1, "KANBAN_TASK_FAILED never fired for store.record_failure()"
    assert fired[0]["task_id"] == task.id
    assert fired[0]["consecutive_failures"] == 1
    assert fired[0]["circuit_broken"] is False


def test_circuit_break_fires_both_failed_and_blocked(store, record):
    task = store.create_task({"title": "doomed", "max_retries": 1})
    seen = record(HookEvent.KANBAN_TASK_FAILED, HookEvent.KANBAN_TASK_BLOCKED)

    assert store.record_failure(task.id, error="exit code 1") is True
    assert len(seen[HookEvent.KANBAN_TASK_FAILED]) == 1
    blocked = seen[HookEvent.KANBAN_TASK_BLOCKED]
    assert len(blocked) == 1, "auto-block by the circuit breaker never fired KANBAN_TASK_BLOCKED"
    assert blocked[0]["task_id"] == task.id


def test_reclaiming_a_stale_claim_fires_moved(store, record):
    task = store.create_task({"title": "stranded", "status": "ready"})
    store.claim_task(task.id, "worker-dead", ttl_seconds=-1, worker_pid=None)
    seen = record(HookEvent.KANBAN_TASK_MOVED)

    assert store.reclaim_stale_claims(stale_timeout_seconds=0) == [task.id]
    fired = seen[HookEvent.KANBAN_TASK_MOVED]
    assert len(fired) == 1, "reclaiming a stranded task never fired KANBAN_TASK_MOVED"
    assert fired[0]["from_status"] == "running"
    assert fired[0]["to_status"] == "ready"


def test_a_failing_hook_never_breaks_the_store(store, record):
    """Hook emission is best-effort: a raising subscriber must not fail the write."""
    record()  # installs the clean registry

    def _boom(_data):
        raise RuntimeError("subscriber exploded")

    add_hook(HookEvent.KANBAN_TASK_CREATED, _boom)
    task = store.create_task({"title": "still works"})
    assert store.get_task(task.id) is not None
