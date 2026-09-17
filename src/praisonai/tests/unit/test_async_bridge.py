"""Unit tests for ``praisonai._async_bridge``.

These cover the contract of the wrapper-layer async bridge that lets sync
callers run coroutines on a shared background event loop:

  - ``run_sync(coro)`` runs the coroutine on a daemon background loop and
    returns its result.
  - ``run_sync()`` raises ``RuntimeError`` when called from inside a
    running event loop instead of deadlocking on ``fut.result()``.
  - The background thread is marked ``daemon=True`` so short-lived
    scripts (CLI commands, smoke tests) exit cleanly without explicit
    shutdown.
  - ``_BackgroundLoop._spawn_locked()`` enforces its
    "caller must hold the lock" contract via an ``assert``.

The helper coroutine below is named ``_coro`` (leading underscore) so
pytest does not collect it as a test of its own — it has a required
parameter and would fail fixture resolution.
"""

import asyncio
import logging
import threading
import unittest
import weakref

from praisonai._async_bridge import (
    _BG,
    DispatchKind,
    dispatch_maybe_awaitable,
    run_sync,
)


async def _coro(value: int) -> int:
    """Helper coroutine used by the tests below."""
    await asyncio.sleep(0)  # yield to the loop at least once
    return value * 2


class TestRunSync(unittest.TestCase):
    def test_runs_coroutine_and_returns_result(self):
        self.assertEqual(run_sync(_coro(21)), 42)

    def test_returns_result_repeatedly(self):
        # Same background loop is reused across calls.
        self.assertEqual(run_sync(_coro(1)), 2)
        self.assertEqual(run_sync(_coro(2)), 4)
        self.assertEqual(run_sync(_coro(3)), 6)

    def test_propagates_coroutine_exceptions(self):
        async def boom() -> None:
            raise ValueError("from coro")

        with self.assertRaises(ValueError) as cm:
            run_sync(boom())
        self.assertEqual(str(cm.exception), "from coro")

    def test_raises_runtime_error_from_inside_running_loop(self):
        """``run_sync()`` must refuse cross-loop reentry instead of deadlocking.

        We verify this by submitting an *outer* coroutine to ``run_sync``;
        from inside that coroutine (which is running on the bridge's loop)
        we call ``run_sync(_coro(1))`` again. The inner call must raise
        ``RuntimeError`` rather than blocking on ``fut.result()``, which
        would deadlock the bridge loop forever.
        """
        async def nested_call() -> bool:
            coro = _coro(1)
            try:
                run_sync(coro)
            except RuntimeError:
                coro.close()  # cleanly cancel the never-awaited coroutine
                return True
            return False

        self.assertTrue(run_sync(nested_call()))

    def test_timeout_cancels_coroutine_and_runs_finally(self):
        cleanup_done = threading.Event()

        async def never_finishes() -> None:
            try:
                await asyncio.Event().wait()
            finally:
                cleanup_done.set()

        with self.assertRaises(TimeoutError):
            run_sync(never_finishes(), timeout=0.01)

        self.assertTrue(
            cleanup_done.wait(timeout=2.0),
            "timed out coroutine should be cancelled and run its cleanup",
        )


class TestBackgroundThread(unittest.TestCase):
    def test_thread_is_daemon_and_alive(self):
        # Force lazy creation of the loop+thread.
        run_sync(_coro(1))
        self.assertIsNotNone(_BG._thread)
        self.assertTrue(_BG._thread.daemon, "background thread must be daemon=True")
        self.assertTrue(_BG._thread.is_alive())

    def test_spawn_locked_requires_lock(self):
        """``_spawn_locked()`` must enforce its caller-holds-lock contract."""
        # The lock is *not* held here, so the call must trip the assert.
        with self.assertRaises(AssertionError):
            _BG._spawn_locked()

    def test_spawn_locked_works_when_lock_held(self):
        """The same call succeeds while the caller holds the lock.

        Mirrors the real calling convention in ``get()``/``submit()``: the
        holder records its identity in ``_lock_owner`` so ``_spawn_locked()``
        can verify the *caller* (not merely *someone*) owns the lock.
        """
        with _BG._lock:
            _BG._lock_owner = threading.get_ident()
            try:
                loop = _BG._spawn_locked()
            finally:
                _BG._lock_owner = None
        self.assertIsNotNone(loop)
        self.assertFalse(loop.is_closed())

    def test_spawn_locked_rejects_foreign_lock_holder(self):
        """A thread that does not own the lock must trip the assert even if
        another thread currently holds ``self._lock``."""
        holding = threading.Event()
        release = threading.Event()

        def _holder():
            with _BG._lock:
                _BG._lock_owner = threading.get_ident()
                holding.set()
                release.wait(timeout=2.0)
                _BG._lock_owner = None

        t = threading.Thread(target=_holder)
        t.start()
        try:
            self.assertTrue(holding.wait(timeout=2.0))
            # Different thread (this one) does not own the lock.
            with self.assertRaises(AssertionError):
                _BG._spawn_locked()
        finally:
            release.set()
            t.join(timeout=2.0)


class TestDispatchMaybeAwaitable(unittest.TestCase):
    """Contract of the shared sync→async dispatch helper.

    ``dispatch_maybe_awaitable`` is the single owner of the submit/track/
    done-callback policy the db adapter's ``_call_store``/``_merge_and_set``/
    ``on_agent_end`` paths route through, so its four branches are pinned here.
    """

    def test_non_awaitable_passthrough(self):
        """A plain (non-awaitable) value is returned as-is, unchanged."""
        sentinel = object()
        self.assertIs(
            dispatch_maybe_awaitable(sentinel, kind=DispatchKind.READ),
            sentinel,
        )
        self.assertEqual(
            dispatch_maybe_awaitable(123, kind=DispatchKind.WRITE),
            123,
        )

    def test_no_loop_read_blocks_and_returns_value(self):
        """No running loop + READ blocks on the bridge and returns the value."""
        self.assertEqual(
            dispatch_maybe_awaitable(_coro(21), kind=DispatchKind.READ),
            42,
        )

    def test_no_loop_write_blocks_and_returns_value(self):
        """No running loop + WRITE also blocks and returns the value.

        Outside a loop there is no reason to defer, so a write is run to
        completion just like a read (fire-and-forget is a running-loop concern).
        """
        self.assertEqual(
            dispatch_maybe_awaitable(_coro(5), kind=DispatchKind.WRITE),
            10,
        )

    def test_running_loop_write_is_tracked_fire_and_forget(self):
        """Running loop + WRITE submits to the bridge, tracks the future, and
        returns ``None`` while the write still completes in the background."""
        tracker: "weakref.WeakSet" = weakref.WeakSet()
        lock = threading.Lock()
        gate = threading.Event()
        done = threading.Event()

        async def _write() -> int:
            # Park until the test has observed the tracked future so the
            # WeakSet cannot GC a completed future before we assert on it.
            await asyncio.get_running_loop().run_in_executor(None, gate.wait, 2.0)
            done.set()
            return 99

        async def _outer():
            return dispatch_maybe_awaitable(
                _write(),
                kind=DispatchKind.WRITE,
                tracker=tracker,
                tracker_lock=lock,
                op_name="unit-write",
            )

        # Run the dispatch from *inside* a running loop (the bridge loop).
        result = run_sync(_outer())
        self.assertIsNone(result, "running-loop WRITE must return None")
        # The in-flight (still-parked) future must be tracked at this point.
        with lock:
            self.assertEqual(len(tracker), 1, "the in-flight future must be tracked")
        # Release the write and confirm it still runs to completion.
        gate.set()
        self.assertTrue(
            done.wait(timeout=2.0),
            "deferred write coroutine should still run to completion",
        )

    def test_running_loop_failed_write_logs_and_does_not_raise(self):
        """A failed deferred write is swallowed (logged) via the done-callback,
        never surfacing to the returning sync caller."""
        tracker: "weakref.WeakSet" = weakref.WeakSet()
        lock = threading.Lock()

        async def _boom() -> None:
            await asyncio.sleep(0)
            raise ValueError("deferred failure")

        async def _outer():
            return dispatch_maybe_awaitable(
                _boom(),
                kind=DispatchKind.WRITE,
                tracker=tracker,
                tracker_lock=lock,
                op_name="unit-fail",
            )

        # Must not raise even though the deferred coroutine fails. The helper's
        # done-callback logs a warning; silence it so the expected traceback
        # does not clutter the test output.
        logging.getLogger("praisonai._async_bridge").setLevel(logging.CRITICAL)
        try:
            self.assertIsNone(run_sync(_outer()))
            with lock:
                futures = list(tracker)
            for f in futures:
                # Give the callback-bearing future a moment to settle.
                try:
                    f.exception(timeout=2.0)
                except Exception:
                    pass
        finally:
            logging.getLogger("praisonai._async_bridge").setLevel(logging.NOTSET)
        # The failure was logged, not propagated to the caller — reaching here
        # without an exception is the assertion.


if __name__ == "__main__":
    unittest.main()
