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
import unittest

from praisonai._async_bridge import _BG, run_sync


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
        """The same call succeeds while the lock is held."""
        with _BG._lock:
            loop = _BG._spawn_locked()
        self.assertIsNotNone(loop)
        self.assertFalse(loop.is_closed())


if __name__ == "__main__":
    unittest.main()
