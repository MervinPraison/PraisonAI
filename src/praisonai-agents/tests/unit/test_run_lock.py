"""Regression tests for the shared lazy run-lock helper (``_run_lock``).

AgentTeam and Workflow/AgentFlow both delegate their ``_execution_lock`` to
``ensure_run_lock``; these tests pin the invariants that delegation relies on:
stable per-instance identity, support for both the plain-attribute and
preset-``None`` dataclass-field cases, and a single shared lock object under a
concurrent first-access race (double-checked locking).
"""
import threading

from praisonaiagents._run_lock import ensure_run_lock


class _PlainAttr:
    """Mimics AgentTeam: ``_run_lock`` is a plain (missing) attribute."""


class _PresetNoneField:
    """Mimics the Workflow dataclass field defaulting to ``None``."""

    def __init__(self):
        self._run_lock = None


def test_mints_and_returns_stable_lock_plain_attribute():
    obj = _PlainAttr()
    lock = ensure_run_lock(obj)
    assert lock is not None
    assert ensure_run_lock(obj) is lock
    assert obj._run_lock is lock


def test_mints_and_returns_stable_lock_preset_none_field():
    obj = _PresetNoneField()
    lock = ensure_run_lock(obj)
    assert lock is not None
    assert ensure_run_lock(obj) is lock
    assert obj._run_lock is lock


def test_distinct_instances_get_distinct_locks():
    assert ensure_run_lock(_PlainAttr()) is not ensure_run_lock(_PlainAttr())


def test_concurrent_first_access_observes_single_lock():
    """Threads racing into the first access must all observe the same lock."""
    obj = _PlainAttr()
    start = threading.Event()
    observed = []
    observed_guard = threading.Lock()

    def _race():
        start.wait(5)
        lock = ensure_run_lock(obj)
        with observed_guard:
            observed.append(lock)

    threads = [threading.Thread(target=_race) for _ in range(16)]
    for t in threads:
        t.start()
    start.set()
    for t in threads:
        t.join(5)

    assert len(observed) == 16
    assert all(lock is observed[0] for lock in observed)
    assert obj._run_lock is observed[0]
