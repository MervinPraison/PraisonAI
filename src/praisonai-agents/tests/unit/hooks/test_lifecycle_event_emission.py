"""Regression tests: declared lifecycle hook events must actually be emitted.

``HookEvent`` declares ``JOB_COMPLETED`` and the six ``KANBAN_TASK_*`` members.
Declaring an event that nothing ever fires is a silent failure: a plugin author
registers a callback and waits forever. These tests register a *real* hook on
the default registry and assert the runtime emits it.
"""

import time

import pytest

from praisonaiagents.hooks.registry import (
    HookRegistry,
    add_hook,
    get_default_registry,
    set_default_registry,
)
from praisonaiagents.hooks.types import HookEvent, HookResult


@pytest.fixture
def clean_registry():
    """Swap in a fresh process-wide default registry for the test."""
    previous = get_default_registry()
    set_default_registry(HookRegistry())
    try:
        yield get_default_registry()
    finally:
        set_default_registry(previous)


def test_fire_hook_is_exported():
    """``fire_hook`` is the emitter callers (e.g. the kanban dispatcher) import."""
    from praisonaiagents.hooks import fire_hook

    assert callable(fire_hook)


def test_fire_hook_reaches_a_registered_kanban_hook(clean_registry):
    """A hook registered on a kanban event receives a fired event."""
    from praisonaiagents.hooks import fire_hook

    seen = []
    add_hook(HookEvent.KANBAN_TASK_MOVED, lambda data: seen.append(data) or HookResult.allow())

    fire_hook(
        HookEvent.KANBAN_TASK_MOVED,
        {"task_id": "t1", "from_status": "todo", "to_status": "ready"},
    )

    assert len(seen) == 1, "hook registered on KANBAN_TASK_MOVED never fired"
    payload = seen[0].to_dict()
    assert payload["event_name"] == "kanban_task_moved"
    assert payload["task_id"] == "t1"
    assert payload["from_status"] == "todo"
    assert payload["to_status"] == "ready"


def test_fire_hook_accepts_enum_member_name(clean_registry):
    """Legacy call sites pass the enum *member name*; it must still route."""
    from praisonaiagents.hooks import fire_hook

    seen = []
    add_hook(HookEvent.KANBAN_TASK_CLAIMED, lambda data: seen.append(data) or HookResult.allow())

    fire_hook("KANBAN_TASK_CLAIMED", {"task_id": "t2", "assignee": "w1"})

    assert len(seen) == 1, "member-name event id did not route to the canonical event"
    assert seen[0].to_dict()["assignee"] == "w1"


def test_fire_hook_is_silent_for_unknown_events(clean_registry):
    """An unknown event id must never raise into the caller."""
    from praisonaiagents.hooks import fire_hook

    assert fire_hook("definitely_not_an_event", {"task_id": "x"}) == []


def test_job_completed_fires_when_a_background_job_succeeds(clean_registry):
    """A background job reaching COMPLETED emits JOB_COMPLETED."""
    from praisonaiagents.background.job_manager import BackgroundJobManager

    seen = []
    add_hook(HookEvent.JOB_COMPLETED, lambda data: seen.append(data) or HookResult.allow())

    manager = BackgroundJobManager(max_workers=1)
    job_id = manager.start_job(lambda: "done-payload")
    manager.get_result(job_id, timeout=10)

    deadline = time.time() + 5
    while not seen and time.time() < deadline:
        time.sleep(0.01)

    assert len(seen) == 1, "JOB_COMPLETED never fired for a successful background job"
    payload = seen[0].to_dict()
    assert payload["event_name"] == "job_completed"
    assert payload["job_id"] == job_id
    assert payload["status"] == "completed"
    assert payload["result"] == "done-payload"


def test_job_completed_fires_when_a_background_job_fails(clean_registry):
    """A background job reaching FAILED emits JOB_COMPLETED with the error."""
    from praisonaiagents.background.job_manager import BackgroundJobManager

    seen = []
    add_hook(HookEvent.JOB_COMPLETED, lambda data: seen.append(data) or HookResult.allow())

    def _boom():
        raise ValueError("kaboom")

    manager = BackgroundJobManager(max_workers=1)
    job_id = manager.start_job(_boom)

    deadline = time.time() + 5
    while not seen and time.time() < deadline:
        time.sleep(0.01)

    assert len(seen) == 1, "JOB_COMPLETED never fired for a failed background job"
    payload = seen[0].to_dict()
    assert payload["job_id"] == job_id
    assert payload["status"] == "failed"
    assert "kaboom" in (payload["error"] or "")


@pytest.mark.asyncio
async def test_fire_hook_delivers_from_inside_a_running_event_loop(clean_registry):
    """The kanban dispatcher emits from ``async def`` code.

    ``HookRunner.execute_sync`` refuses to run inside a live loop, so a naive
    emitter would raise there and the event would be swallowed. Emission must
    instead be scheduled on the running loop and still reach the subscriber.
    """
    import asyncio

    from praisonaiagents.hooks import fire_hook

    seen = []
    add_hook(HookEvent.KANBAN_TASK_DONE, lambda data: seen.append(data) or HookResult.allow())

    fire_hook(HookEvent.KANBAN_TASK_DONE, {"task_id": "t9", "status": "done"})

    for _ in range(200):
        if seen:
            break
        await asyncio.sleep(0.01)

    assert len(seen) == 1, "KANBAN_TASK_DONE never reached the hook from a running loop"
    assert seen[0].to_dict()["task_id"] == "t9"
