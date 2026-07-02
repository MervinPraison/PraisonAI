"""Shared SQLite-backed delivery-control state (issue #2579).

Covers the ``DeliveryControlStore`` and its integration with ``RateLimiter``
(cross-worker token bucket) and ``DeadTargetRegistry`` (row-based, restart-safe).
"""
from __future__ import annotations

import time

import pytest

try:
    from praisonai.bots._delivery_control_store import DeliveryControlStore
    from praisonai.bots._rate_limit import RateLimiter, RateLimitConfig
    from praisonai.bots._dead_targets import DeadTargetRegistry
except ImportError:  # pragma: no cover - CI without deps
    pytest.skip("praisonai.bots dependencies not available", allow_module_level=True)


# ─── DeliveryControlStore: rate-limit token reservation ──────────────
class TestSharedRateLimitStore:
    def test_first_reservation_no_wait(self, tmp_path):
        store = DeliveryControlStore(tmp_path / "ctl.sqlite")
        wait = store.reserve_tokens(
            "telegram",
            now=time.time(),
            burst_size=5,
            messages_per_second=1.0,
            channel_id=None,
            per_channel_delay=0.0,
        )
        assert wait == 0.0

    def test_burst_exhaustion_forces_wait(self, tmp_path):
        store = DeliveryControlStore(tmp_path / "ctl.sqlite")
        now = time.time()
        # burst_size=1 -> first is free, second must wait ~1/mps.
        first = store.reserve_tokens(
            "t", now=now, burst_size=1, messages_per_second=1.0,
            channel_id=None, per_channel_delay=0.0,
        )
        second = store.reserve_tokens(
            "t", now=now, burst_size=1, messages_per_second=1.0,
            channel_id=None, per_channel_delay=0.0,
        )
        assert first == 0.0
        assert second == pytest.approx(1.0, abs=0.05)

    def test_two_limiters_share_one_bucket(self, tmp_path):
        # The core issue: N workers with the SAME store/scope must share the
        # ceiling. Two separate limiter instances pointed at one store should
        # NOT both get a free burst token beyond burst_size.
        store = DeliveryControlStore(tmp_path / "ctl.sqlite")
        now = time.time()
        # burst_size=1 shared: first limiter's send is free, the second
        # limiter's send draws from the same (now empty) bucket and must wait.
        w1 = store.reserve_tokens(
            "telegram", now=now, burst_size=1, messages_per_second=1.0,
            channel_id=None, per_channel_delay=0.0,
        )
        w2 = store.reserve_tokens(
            "telegram", now=now, burst_size=1, messages_per_second=1.0,
            channel_id=None, per_channel_delay=0.0,
        )
        assert w1 == 0.0
        assert w2 > 0.0  # shared ceiling enforced across "workers"

    def test_different_scopes_independent(self, tmp_path):
        store = DeliveryControlStore(tmp_path / "ctl.sqlite")
        now = time.time()
        w1 = store.reserve_tokens(
            "telegram", now=now, burst_size=1, messages_per_second=1.0,
            channel_id=None, per_channel_delay=0.0,
        )
        w2 = store.reserve_tokens(
            "discord", now=now, burst_size=1, messages_per_second=1.0,
            channel_id=None, per_channel_delay=0.0,
        )
        assert w1 == 0.0 and w2 == 0.0  # separate buckets

    def test_per_channel_delay(self, tmp_path):
        store = DeliveryControlStore(tmp_path / "ctl.sqlite")
        now = time.time()
        store.reserve_tokens(
            "t", now=now, burst_size=10, messages_per_second=100.0,
            channel_id="c1", per_channel_delay=1.0,
        )
        wait = store.reserve_tokens(
            "t", now=now, burst_size=10, messages_per_second=100.0,
            channel_id="c1", per_channel_delay=1.0,
        )
        assert wait == pytest.approx(1.0, abs=0.05)

    def test_global_penalty_holds_off(self, tmp_path):
        store = DeliveryControlStore(tmp_path / "ctl.sqlite")
        now = time.time()
        store.penalise("t", None, until=now + 5.0)
        wait = store.reserve_tokens(
            "t", now=now, burst_size=10, messages_per_second=100.0,
            channel_id=None, per_channel_delay=0.0,
        )
        assert wait == pytest.approx(5.0, abs=0.1)

    def test_channel_penalty_holds_off(self, tmp_path):
        store = DeliveryControlStore(tmp_path / "ctl.sqlite")
        now = time.time()
        store.penalise("t", "c1", until=now + 3.0)
        wait = store.reserve_tokens(
            "t", now=now, burst_size=10, messages_per_second=100.0,
            channel_id="c1", per_channel_delay=0.0,
        )
        assert wait == pytest.approx(3.0, abs=0.1)

    def test_state_survives_new_store_instance(self, tmp_path):
        # Restart: a fresh store on the same file sees prior token state.
        path = tmp_path / "ctl.sqlite"
        now = time.time()
        s1 = DeliveryControlStore(path)
        s1.reserve_tokens(
            "t", now=now, burst_size=1, messages_per_second=1.0,
            channel_id=None, per_channel_delay=0.0,
        )
        s2 = DeliveryControlStore(path)
        wait = s2.reserve_tokens(
            "t", now=now, burst_size=1, messages_per_second=1.0,
            channel_id=None, per_channel_delay=0.0,
        )
        assert wait > 0.0  # bucket already drained by s1

    def test_reset_clears_scope(self, tmp_path):
        store = DeliveryControlStore(tmp_path / "ctl.sqlite")
        now = time.time()
        store.reserve_tokens(
            "t", now=now, burst_size=1, messages_per_second=1.0,
            channel_id=None, per_channel_delay=0.0,
        )
        store.reset_rate_limit("t")
        wait = store.reserve_tokens(
            "t", now=now, burst_size=1, messages_per_second=1.0,
            channel_id=None, per_channel_delay=0.0,
        )
        assert wait == 0.0  # bucket refilled after reset


# ─── RateLimiter integration ─────────────────────────────────────────
class TestRateLimiterSharedBackend:
    @pytest.mark.asyncio
    @pytest.mark.allow_sleep
    async def test_acquire_uses_shared_store(self, tmp_path):
        store = DeliveryControlStore(tmp_path / "ctl.sqlite")
        cfg = RateLimitConfig(messages_per_second=100.0, per_channel_delay=0.0, burst_size=5)
        a = RateLimiter(cfg, store=store, scope="telegram")
        b = RateLimiter(cfg, store=store, scope="telegram")
        # Both share the same scope; the first quickly acquires without error.
        await a.acquire("c1")
        await b.acquire("c1")

    @pytest.mark.asyncio
    async def test_default_no_store_stays_in_memory(self, tmp_path):
        # Backward compat: no store means no SQLite file is created.
        lim = RateLimiter(RateLimitConfig(messages_per_second=100.0, burst_size=5))
        assert lim._store is None
        await lim.acquire("c1")

    @pytest.mark.asyncio
    async def test_for_platform_with_store_scopes_by_platform(self, tmp_path):
        store = DeliveryControlStore(tmp_path / "ctl.sqlite")
        lim = RateLimiter.for_platform("telegram", store=store)
        assert lim._scope == "telegram"
        await lim.acquire("c1")

    @pytest.mark.asyncio
    async def test_penalise_via_store(self, tmp_path):
        store = DeliveryControlStore(tmp_path / "ctl.sqlite")
        cfg = RateLimitConfig(messages_per_second=100.0, per_channel_delay=0.0, burst_size=10)
        lim = RateLimiter(cfg, store=store, scope="t")
        await lim.penalise("c1", 2.0)
        # The penalty is now visible to a fresh limiter on the same store.
        lim2 = RateLimiter(cfg, store=store, scope="t")
        wait = await _measure_wait(lim2, "c1")
        assert wait >= 1.0


async def _measure_wait(limiter, channel):
    start = time.monotonic()
    # Reserve directly through the store to read the wait without sleeping.
    return limiter._store.reserve_tokens(
        limiter._scope,
        now=time.time(),
        burst_size=float(limiter._config.burst_size),
        messages_per_second=limiter._config.messages_per_second,
        channel_id=channel,
        per_channel_delay=limiter._config.per_channel_delay,
    )


# ─── DeadTargetRegistry integration ──────────────────────────────────
class TestDeadTargetRegistrySharedBackend:
    def test_mark_is_dead_clear(self, tmp_path):
        store = DeliveryControlStore(tmp_path / "ctl.sqlite")
        reg = DeadTargetRegistry(store=store)
        assert reg.is_dead("telegram", "-1001") is False
        reg.mark_dead("telegram", "-1001", reason="403")
        assert reg.is_dead("telegram", "-1001") is True
        assert reg.size() == 1
        reg.clear("telegram", "-1001")
        assert reg.is_dead("telegram", "-1001") is False
        assert reg.size() == 0

    def test_survives_new_registry_instance(self, tmp_path):
        path = tmp_path / "ctl.sqlite"
        store = DeliveryControlStore(path)
        reg = DeadTargetRegistry(store=store)
        reg.mark_dead("telegram", "-1001", reason="403 kicked")
        # New store + registry on the same file (restart / another worker).
        reg2 = DeadTargetRegistry(store=DeliveryControlStore(path))
        assert reg2.is_dead("telegram", "-1001") is True
        assert reg2.list_dead()[0].reason == "403 kicked"

    def test_case_insensitive_platform(self, tmp_path):
        store = DeliveryControlStore(tmp_path / "ctl.sqlite")
        reg = DeadTargetRegistry(store=store)
        reg.mark_dead("Telegram", "-1001", reason="403")
        assert reg.is_dead("TELEGRAM", "-1001") is True

    def test_max_size_bound(self, tmp_path):
        store = DeliveryControlStore(tmp_path / "ctl.sqlite")
        reg = DeadTargetRegistry(store=store, max_size=2)
        reg.mark_dead("p", "1", reason="r")
        time.sleep(0.01)
        reg.mark_dead("p", "2", reason="r")
        time.sleep(0.01)
        reg.mark_dead("p", "3", reason="r")
        assert reg.size() == 2
        assert reg.is_dead("p", "1") is False
        assert reg.is_dead("p", "3") is True

    def test_ttl_expiry(self, tmp_path):
        store = DeliveryControlStore(tmp_path / "ctl.sqlite")
        reg = DeadTargetRegistry(store=store, ttl_seconds=1)
        reg.mark_dead("telegram", "-1001", reason="403")
        # Force ts into the past directly in the store.
        store.dead_clear("telegram", "-1001")
        import sqlite3
        conn = sqlite3.connect(str(store.path))
        conn.execute(
            "INSERT INTO dead_targets(platform, channel_id, reason, ts) "
            "VALUES (?, ?, ?, ?)",
            ("telegram", "-1001", "403", time.time() - 10),
        )
        conn.commit()
        conn.close()
        assert reg.is_dead("telegram", "-1001") is False

    def test_reprobe_after_interval(self, tmp_path):
        import sqlite3
        store = DeliveryControlStore(tmp_path / "ctl.sqlite")
        reg = DeadTargetRegistry(store=store, reprobe_seconds=1)
        reg.mark_dead("telegram", "-1001", reason="403")
        assert reg.should_reprobe("telegram", "-1001") is False
        conn = sqlite3.connect(str(store.path))
        conn.execute(
            "UPDATE dead_targets SET ts = ? WHERE platform = ? AND channel_id = ?",
            (time.time() - 10, "telegram", "-1001"),
        )
        conn.commit()
        conn.close()
        assert reg.should_reprobe("telegram", "-1001") is True

    def test_clear_unknown_is_noop(self, tmp_path):
        store = DeliveryControlStore(tmp_path / "ctl.sqlite")
        reg = DeadTargetRegistry(store=store)
        reg.clear("slack", "C1")  # must not raise
        assert reg.size() == 0


# ─── Export ──────────────────────────────────────────────────────────
def test_exported_from_bots_package():
    from praisonai.bots import DeliveryControlStore as Exported

    assert Exported is DeliveryControlStore
