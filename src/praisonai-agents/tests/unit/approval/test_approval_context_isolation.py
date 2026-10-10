"""Per-context approval cache: copy-on-write, and never touched from a GC finalizer.

Two defects shared one root, the ``_approved_context`` ContextVar holding a
*mutable* set:

* ``mark_approved`` added to that set in place. ``contextvars.copy_context()``
  (used for worker threads and tasks) copies the mapping, not the set, so an
  approval granted inside a child context appeared in the parent and in every
  sibling copied from it.
* ``Agent.__del__`` called ``release_scope``, which rewrote the ContextVar. A
  finalizer runs in whichever thread and context the garbage collector happens
  to fire in, possibly in the middle of another ContextVar update. CI workers
  segfaulted at ContextVar operations and the xdist run then hung until the
  45-minute job timeout.
"""
import contextvars
import gc

import pytest

from praisonaiagents.approval import get_approval_registry


@pytest.fixture
def registry():
    reg = get_approval_registry()
    token = reg._approved_context.set(set())
    try:
        yield reg
    finally:
        reg._approved_context.reset(token)


def test_approval_granted_in_a_copied_context_does_not_leak_to_the_parent(registry):
    registry.mark_approved("seed", {}, scope_id="parent")
    child = contextvars.copy_context()

    child.run(registry.mark_approved, "delete_file", {"path": "/x"}, scope_id="worker")

    assert child.run(registry.is_already_approved, "delete_file", {"path": "/x"}, scope_id="worker")
    assert not registry.is_already_approved("delete_file", {"path": "/x"}, scope_id="worker")
    assert registry.is_already_approved("seed", {}, scope_id="parent")


def test_sibling_contexts_do_not_share_approvals(registry):
    registry.mark_approved("seed", {}, scope_id="s")
    a, b = contextvars.copy_context(), contextvars.copy_context()

    a.run(registry.mark_approved, "send_email", {"to": "x"}, scope_id="s")

    assert not b.run(registry.is_already_approved, "send_email", {"to": "x"}, scope_id="s")


def test_mark_approved_never_mutates_the_set_it_read(registry):
    before = registry._approved_context.get()
    registry.mark_approved("t", {}, scope_id="s")
    assert before == set()
    assert registry.is_already_approved("t", {}, scope_id="s")


def test_release_scope_without_context_eviction_leaves_the_contextvar_alone(registry):
    registry.mark_approved("t", {}, scope_id="dead")
    seen = registry._approved_context.get()

    registry.release_scope("dead", evict_context_cache=False)

    assert registry._approved_context.get() is seen


def test_release_scope_still_evicts_by_default(registry):
    registry.mark_approved("t", {}, scope_id="dead")
    registry.mark_approved("t", {}, scope_id="live")

    registry.release_scope("dead")

    assert not registry.is_already_approved("t", {}, scope_id="dead")
    assert registry.is_already_approved("t", {}, scope_id="live")


def test_agent_finalizer_does_not_write_the_approval_contextvar(registry):
    from praisonaiagents import Agent

    agent = Agent(instructions="x")
    registry.mark_approved("t", {}, scope_id=agent._approval_scope_id)
    seen = registry._approved_context.get()

    agent.__del__()

    assert registry._approved_context.get() is seen


def test_agent_finalizer_still_releases_process_global_grants(registry):
    from praisonaiagents import Agent

    agent = Agent(instructions="x")
    sid = agent._approval_scope_id
    registry.auto_approve_tool("write_file", sid)
    assert any(k[0] == sid for k in registry._agent_tool_auto_approve)

    agent.__del__()

    assert not any(k[0] == sid for k in registry._agent_tool_auto_approve)


def test_explicit_close_still_evicts_the_callers_context(registry):
    from praisonaiagents import Agent

    agent = Agent(instructions="x")
    registry.mark_approved("t", {}, scope_id=agent._approval_scope_id)

    agent.close()

    assert not registry.is_already_approved("t", {}, scope_id=agent._approval_scope_id)


def test_collecting_many_agents_mid_contextvar_traffic_is_safe(registry):
    """Smoke: finalizers firing during ContextVar churn must not touch the cache."""
    from praisonaiagents import Agent

    old = gc.get_threshold()
    gc.set_threshold(5, 1, 1)
    try:
        for i in range(30):
            Agent(instructions="x")
            registry.mark_approved("t", {"i": i % 3}, scope_id="churn")
        gc.collect()
    finally:
        gc.set_threshold(*old)
    assert registry.is_already_approved("t", {"i": 0}, scope_id="churn")
