"""Parallel tool calls share one LoopGuard per turn (#6277).

The no-progress halt only sees finished calls, so a parallel batch of repeat
calls could run past the point where a sequential run stops. An allowed
pre-execution check now reserves its call until record() lands, and in-flight
calls to the tool on a stuck streak count toward that streak.
"""
import threading

from praisonaiagents.escalation.loop_guard import LoopGuard

ARGS = {"path": "a.py"}


def _sequential_allowed(limit=30):
    guard, allowed = LoopGuard(), 0
    for _ in range(limit):
        if guard.check("read_file", ARGS).should_block():
            break
        allowed += 1
        guard.record("read_file", ARGS, True, result="same")
    return allowed


def _parallel_allowed(batch, limit_batches=10):
    guard, allowed = LoopGuard(), 0
    for _ in range(limit_batches):
        barrier, decisions = threading.Barrier(batch), [None] * batch

        def worker(i):
            barrier.wait()
            decisions[i] = guard.check("read_file", ARGS)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(batch)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        ok = [d for d in decisions if not d.should_block()]
        for _ in ok:
            guard.record("read_file", ARGS, True, result="same")
        allowed += len(ok)
        if not ok:
            break
    return allowed


def test_parallel_batches_stop_where_sequential_stops():
    expected = _sequential_allowed()
    assert expected == 8  # default no_progress_halt
    for batch in (2, 3, 5):
        assert _parallel_allowed(batch) == expected


def test_progress_is_not_projected():
    # Different results are progress: in-flight calls must not cause a halt.
    guard = LoopGuard()
    for i in range(3):
        assert not guard.check("read_file", ARGS).should_block()
        guard.record("read_file", ARGS, True, result=f"changed-{i}")
    for _ in range(5):
        assert not guard.check("read_file", ARGS).should_block()


def test_record_releases_reservation_and_reset_clears():
    guard = LoopGuard()
    guard.check("read_file", ARGS)
    assert guard._in_flight == {"read_file": 1}
    guard.record("read_file", ARGS, True, result="x")
    assert guard._in_flight == {"read_file": 0}
    guard.check("other", {})
    guard.reset_turn()
    assert guard._in_flight == {}
