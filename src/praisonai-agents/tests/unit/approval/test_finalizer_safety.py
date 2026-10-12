"""Garbage-collection finalizers must never block, and dead agents' cache keys must not pile up.

* ``Agent.__del__`` reached the registry through ``get_approval_registry()``,
  which takes a non-reentrant module lock. A collection triggered while that
  lock was held on the same thread (first registry construction) deadlocked.
* ``mark_approved`` is copy-on-write per context. Agents that were never
  ``close()``d left their keys in a long-lived context forever, and every
  later ``mark_approved`` copied the whole, growing set.
"""
import threading
import uuid

import pytest

import praisonaiagents.approval as approval_mod
from praisonaiagents.approval import get_approval_registry
from praisonaiagents.approval.registry import ApprovalRegistry


@pytest.fixture
def registry():
    reg = get_approval_registry()
    token = reg._approved_context.set(None)
    try:
        yield reg
    finally:
        reg._approved_context.reset(token)


def _run_with_timeout(fn, seconds=3.0):
    done = threading.Event()
    def target():
        fn()
        done.set()
    t = threading.Thread(target=target, daemon=True)
    t.start()
    return done.wait(seconds)


def test_agent_finalizer_does_not_take_the_module_registry_lock():
    from praisonaiagents import Agent

    agent = Agent(instructions="x")
    get_approval_registry()  # registry exists
    with approval_mod._registry_lock:   # GC fires while this thread holds it
        assert _run_with_timeout(agent.__del__), "Agent.__del__ blocked on _registry_lock"


def test_agent_finalizer_before_any_registry_exists_is_a_no_op(monkeypatch):
    from praisonaiagents import Agent

    agent = Agent(instructions="x")
    monkeypatch.setattr(approval_mod, "_registry", None)
    agent.__del__()
    assert approval_mod._registry is None, "finalizer must not build a registry"


def test_keys_of_a_finalized_agent_are_pruned_on_the_next_write(registry):
    # Real scope ids are per-instance UUIDs and never repeat.
    dead, live = f"dead-{uuid.uuid4().hex}", f"live-{uuid.uuid4().hex}"
    registry.mark_approved("t", {"i": 1}, scope_id=dead)
    registry.mark_approved("t", {"i": 2}, scope_id=dead)
    registry.mark_approved("t", {"i": 1}, scope_id=live)

    registry.release_scope(dead, from_finalizer=True)   # GC path: no ContextVar write
    assert registry.is_already_approved("t", {"i": 1}, scope_id=dead)

    registry.mark_approved("t", {"i": 2}, scope_id=live)  # next normal write prunes

    assert not registry.is_already_approved("t", {"i": 1}, scope_id=dead)
    assert not registry.is_already_approved("t", {"i": 2}, scope_id=dead)
    assert registry.is_already_approved("t", {"i": 1}, scope_id=live)
    assert registry.is_already_approved("t", {"i": 2}, scope_id=live)


def test_context_cache_is_bounded_and_keeps_the_newest(registry):
    cap = ApprovalRegistry._MAX_CONTEXT_APPROVALS
    sid = f"cap-{uuid.uuid4().hex}"
    for i in range(cap + 50):
        registry.mark_approved("t", {"i": i}, scope_id=sid)

    assert len(registry._approved_context.get()) == cap
    assert registry.is_already_approved("t", {"i": cap + 49}, scope_id=sid)
    assert not registry.is_already_approved("t", {"i": 0}, scope_id=sid)


def test_unclosed_agents_in_a_long_lived_context_do_not_accumulate(registry):
    from praisonaiagents import Agent

    def lookup(q: str) -> str:
        """t"""
        return q

    for i in range(60):
        a = Agent(name="assistant", instructions="x", tools=[lookup])
        a.execute_tool("lookup", {"q": f"r{i}"})
        a.__del__()          # what the collector does for a never-closed agent
        del a
    # Every dead agent's key is pruned by the next agent's write; at most the
    # last one remains.
    assert len(registry._approved_context.get()) <= 1


def test_legacy_set_keys_keep_their_full_scope_id(registry):
    scope = f"Agent:{uuid.uuid4().hex}"
    registry._approved_context.set({registry._approval_cache_key("t", {"a": 1}, scope_id=scope)})
    registry.mark_approved("other", {}, scope_id="*")   # converts the set to a dict
    registry.release_scope(scope)
    assert not registry.is_already_approved("t", {"a": 1}, scope_id=scope)
