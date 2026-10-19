"""Cluster-wide auth rate limiting via Redis (Issue #5914)."""

import time

from praisonai_bot.gateway.rate_limiter import (
    AuthRateLimiter,
    RedisAuthRateLimiter,
    build_auth_rate_limiter,
)


class FakeRedis:
    """Minimal shared store emulating the ``_ALLOW_LUA`` script semantics."""

    def __init__(self):
        self.data = {}  # key -> (value, expires_at)
        self.fail = False

    def _get(self, key):
        item = self.data.get(key)
        if item and item[1] is not None and time.time() >= item[1]:
            self.data.pop(key, None)
            return None
        return item

    def _check(self):
        if self.fail:
            raise ConnectionError("redis down")

    def eval(self, script, numkeys, bucket, lockout, window_ms, max_attempts, lockout_ms):
        self._check()
        if self._get(lockout):
            return 0
        item = self._get(bucket)
        count = (item[0] if item else 0) + 1
        expires = item[1] if item else time.time() + window_ms / 1000.0
        self.data[bucket] = (count, expires)
        if count > max_attempts:
            self.data[lockout] = (1, time.time() + lockout_ms / 1000.0)
            self.data.pop(bucket, None)
            return 0
        return 1

    def delete(self, *keys):
        self._check()
        for k in keys:
            self.data.pop(k, None)

    def pttl(self, key):
        self._check()
        item = self._get(key)
        if not item:
            return -2
        return int((item[1] - time.time()) * 1000)


def test_limit_is_shared_across_replicas():
    redis = FakeRedis()
    replicas = [RedisAuthRateLimiter(redis, max_attempts=5) for _ in range(3)]
    results = [replicas[i % 3].allow("magic_link", "1.2.3.4") for i in range(15)]
    assert results[:5] == [True] * 5
    assert not any(results[5:])
    assert replicas[2].time_until_allowed("magic_link", "1.2.3.4") > 0
    # Other identities are unaffected.
    assert replicas[0].allow("magic_link", "5.6.7.8")


def test_reset_clears_shared_state():
    redis = FakeRedis()
    a, b = RedisAuthRateLimiter(redis, max_attempts=1), RedisAuthRateLimiter(redis, max_attempts=1)
    assert a.allow("auth", "ip")
    assert not b.allow("auth", "ip")
    a.reset("auth", "ip")
    assert b.allow("auth", "ip")


def test_redis_outage_falls_back_to_local_limits():
    redis = FakeRedis()
    redis.fail = True
    limiter = RedisAuthRateLimiter(redis, max_attempts=2)
    assert limiter.allow("auth", "ip")
    assert limiter.allow("auth", "ip")
    assert not limiter.allow("auth", "ip")  # never fails open
    assert limiter.time_until_allowed("auth", "ip") > 0


def test_builder_defaults_to_in_process_limiter():
    assert type(build_auth_rate_limiter(None, max_attempts=3)) is AuthRateLimiter
