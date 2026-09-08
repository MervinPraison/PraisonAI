"""Regression tests for ``LazyCache`` transient-failure cool-down (#4945).

Covers the four cases called out in review:
  * a transient failure is re-raised (cached) *before* the cool-down expires;
  * the loader is retried *after* the cool-down expires;
  * a structural failure stays cached for the process lifetime (no retry);
  * ``reset`` clears both the value cache and the failure-timestamp map.
"""
import unittest

from praisonai._lazy_cache import LazyCache


class _Clock:
    """Deterministic stand-in for ``time.monotonic``."""

    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class TestLazyCacheCooldown(unittest.TestCase):
    def setUp(self):
        self.clock = _Clock()
        # Patch the module clock so cool-down math is deterministic.
        import praisonai._lazy_cache as mod

        self._mod = mod
        self._real_monotonic = mod.time.monotonic
        mod.time.monotonic = self.clock

    def tearDown(self):
        self._mod.time.monotonic = self._real_monotonic

    def test_transient_failure_is_cached_before_cooldown(self):
        cache = LazyCache(retry_cooldown=30.0)
        calls = {"n": 0}

        def loader():
            calls["n"] += 1
            raise ConnectionError("blip")

        with self.assertRaises(ConnectionError):
            cache.get("k", loader)
        self.assertEqual(calls["n"], 1)

        # Still inside the cool-down window: cached error re-raised, no retry.
        self.clock.advance(10.0)
        with self.assertRaises(ConnectionError):
            cache.get("k", loader)
        self.assertEqual(calls["n"], 1, "loader must NOT be retried before cooldown")

    def test_transient_failure_retried_after_cooldown(self):
        cache = LazyCache(retry_cooldown=30.0)
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise TimeoutError("transient")
            return "recovered"

        with self.assertRaises(TimeoutError):
            cache.get("k", flaky)

        # Advance past the cool-down: the loader is retried and now succeeds.
        self.clock.advance(31.0)
        self.assertEqual(cache.get("k", flaky), "recovered")
        self.assertEqual(calls["n"], 2)

        # Success is memoised: no further loader calls.
        self.assertEqual(cache.get("k", flaky), "recovered")
        self.assertEqual(calls["n"], 2)

    def test_structural_failure_is_cached_permanently(self):
        cache = LazyCache(retry_cooldown=30.0)
        calls = {"n": 0}

        def broken():
            calls["n"] += 1
            raise ImportError("no such module")

        with self.assertRaises(ImportError):
            cache.get("k", broken)

        # Even far past any cool-down, a structural failure never retries.
        self.clock.advance(10_000.0)
        with self.assertRaises(ImportError):
            cache.get("k", broken)
        self.assertEqual(calls["n"], 1, "structural failure must not be retried")

    def test_reset_clears_cached_failure_and_timestamp(self):
        cache = LazyCache(retry_cooldown=30.0)
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("transient")
            return "ok"

        with self.assertRaises(OSError):
            cache.get("k", flaky)
        self.assertIn("k", cache._error_ts)

        cache.reset("k")
        self.assertNotIn("k", cache._error_ts)
        self.assertNotIn("k", cache._cache)

        # After reset the loader is retried immediately (no cool-down wait).
        self.assertEqual(cache.get("k", flaky), "ok")
        self.assertEqual(calls["n"], 2)

    def test_reset_all_clears_everything(self):
        cache = LazyCache()
        cache.get("a", lambda: "va")
        with self.assertRaises(ConnectionError):
            cache.get("b", self._raise_conn)
        cache.reset()
        self.assertEqual(cache._cache, {})
        self.assertEqual(cache._error_ts, {})

    @staticmethod
    def _raise_conn():
        raise ConnectionError("x")


if __name__ == "__main__":
    unittest.main()
