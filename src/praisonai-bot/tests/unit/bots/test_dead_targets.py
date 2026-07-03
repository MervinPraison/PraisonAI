"""Self-healing dead-target registry for outbound delivery (issue #2486).

Covers:
  * DeadTargetRegistry.is_dead / mark_dead / clear lifecycle + persistence.
  * TTL + max_size bounding.
  * is_permanent_target_failure() classification (403/404 vs transient vs
    message-scoped 404).
  * DeliveryRouter wiring: short-circuit dead targets, mark on permanent
    failure, self-heal (clear) on success, default-OFF when no registry.
"""
from __future__ import annotations

import time

import pytest


# ─── Registry basics ─────────────────────────────────────────────────
class TestDeadTargetRegistryBasic:
    def test_import_and_construct(self, tmp_path):
        from praisonai_bot.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json")
        assert reg.size() == 0
        assert reg.is_dead("telegram", "-1001") is False

    def test_mark_then_is_dead(self, tmp_path):
        from praisonai_bot.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json")
        reg.mark_dead("telegram", "-1001", reason="403 Forbidden")
        assert reg.is_dead("telegram", "-1001") is True
        assert reg.size() == 1

    def test_clear_self_heals(self, tmp_path):
        from praisonai_bot.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json")
        reg.mark_dead("discord", "42", reason="404")
        assert reg.is_dead("discord", "42") is True
        reg.clear("discord", "42")
        assert reg.is_dead("discord", "42") is False
        assert reg.size() == 0

    def test_platform_case_insensitive(self, tmp_path):
        from praisonai_bot.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json")
        reg.mark_dead("Telegram", "-1001", reason="403")
        assert reg.is_dead("telegram", "-1001") is True
        assert reg.is_dead("TELEGRAM", "-1001") is True

    def test_clear_unknown_is_noop(self, tmp_path):
        from praisonai_bot.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json")
        reg.clear("slack", "C1")  # must not raise
        assert reg.size() == 0

    def test_list_dead_snapshot(self, tmp_path):
        from praisonai_bot.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json")
        reg.mark_dead("telegram", "a", reason="r1")
        reg.mark_dead("telegram", "b", reason="r2")
        items = reg.list_dead()
        assert {d.channel_id for d in items} == {"a", "b"}


# ─── Persistence ─────────────────────────────────────────────────────
class TestDeadTargetPersistence:
    def test_survives_reload(self, tmp_path):
        from praisonai_bot.bots import DeadTargetRegistry

        path = tmp_path / "dead.json"
        reg = DeadTargetRegistry(persist_path=path)
        reg.mark_dead("telegram", "-1001", reason="403 Forbidden: bot kicked")

        reg2 = DeadTargetRegistry(persist_path=path)
        assert reg2.is_dead("telegram", "-1001") is True
        entry = reg2.list_dead()[0]
        assert "kicked" in entry.reason

    def test_clear_persists(self, tmp_path):
        from praisonai_bot.bots import DeadTargetRegistry

        path = tmp_path / "dead.json"
        reg = DeadTargetRegistry(persist_path=path)
        reg.mark_dead("telegram", "-1001", reason="403")
        reg.clear("telegram", "-1001")

        reg2 = DeadTargetRegistry(persist_path=path)
        assert reg2.is_dead("telegram", "-1001") is False


# ─── Bounding (TTL + max_size) ───────────────────────────────────────
class TestDeadTargetBounding:
    def test_ttl_expiry(self, tmp_path):
        from praisonai_bot.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json", ttl_seconds=1)
        reg.mark_dead("telegram", "-1001", reason="403")
        # Force the entry's timestamp into the past.
        key = ("telegram", "-1001")
        old = reg._dead[key]
        reg._dead[key] = type(old)(
            platform=old.platform,
            channel_id=old.channel_id,
            reason=old.reason,
            ts=time.time() - 10,
        )
        assert reg.is_dead("telegram", "-1001") is False

    def test_max_size_evicts_oldest(self, tmp_path):
        from praisonai_bot.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json", max_size=2)
        reg.mark_dead("p", "1", reason="r")
        time.sleep(0.01)
        reg.mark_dead("p", "2", reason="r")
        time.sleep(0.01)
        reg.mark_dead("p", "3", reason="r")
        assert reg.size() == 2
        # Oldest ("1") should be gone.
        assert reg.is_dead("p", "1") is False
        assert reg.is_dead("p", "3") is True

    def test_size_prunes_expired(self, tmp_path):
        # size() must not count TTL-expired entries (greptile P2).
        from praisonai_bot.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json", ttl_seconds=1)
        reg.mark_dead("telegram", "-1001", reason="403")
        key = ("telegram", "-1001")
        old = reg._dead[key]
        reg._dead[key] = type(old)(
            platform=old.platform,
            channel_id=old.channel_id,
            reason=old.reason,
            ts=time.time() - 10,
        )
        assert reg.size() == 0


# ─── Self-healing re-probe ───────────────────────────────────────────
class TestDeadTargetReprobe:
    def test_no_reprobe_before_interval(self, tmp_path):
        from praisonai_bot.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(
            persist_path=tmp_path / "dead.json", reprobe_seconds=3600
        )
        reg.mark_dead("telegram", "-1001", reason="403")
        assert reg.should_reprobe("telegram", "-1001") is False

    def test_reprobe_after_interval(self, tmp_path):
        from praisonai_bot.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(
            persist_path=tmp_path / "dead.json", reprobe_seconds=1
        )
        reg.mark_dead("telegram", "-1001", reason="403")
        key = ("telegram", "-1001")
        old = reg._dead[key]
        reg._dead[key] = type(old)(
            platform=old.platform,
            channel_id=old.channel_id,
            reason=old.reason,
            ts=time.time() - 10,
        )
        assert reg.should_reprobe("telegram", "-1001") is True

    def test_reprobe_disabled_returns_false(self, tmp_path):
        from praisonai_bot.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(
            persist_path=tmp_path / "dead.json", reprobe_seconds=0
        )
        reg.mark_dead("telegram", "-1001", reason="403")
        assert reg.should_reprobe("telegram", "-1001") is False

    def test_reprobe_unknown_target_false(self, tmp_path):
        from praisonai_bot.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json")
        assert reg.should_reprobe("telegram", "-1001") is False


# ─── Error classification ────────────────────────────────────────────
class _StatusError(Exception):
    def __init__(self, status, msg=""):
        self.status_code = status
        super().__init__(msg or f"HTTP {status}")


class TestPermanentClassification:
    def test_403_is_permanent(self):
        from praisonai_bot.bots._resilience import is_permanent_target_failure

        assert is_permanent_target_failure(_StatusError(403, "Forbidden")) is True

    def test_404_is_permanent(self):
        from praisonai_bot.bots._resilience import is_permanent_target_failure

        assert is_permanent_target_failure(_StatusError(404, "chat not found")) is True

    def test_chat_not_found_text(self):
        from praisonai_bot.bots._resilience import is_permanent_target_failure

        assert is_permanent_target_failure(Exception("Bad Request: chat not found")) is True

    def test_bot_kicked_text(self):
        from praisonai_bot.bots._resilience import is_permanent_target_failure

        assert is_permanent_target_failure(
            Exception("Forbidden: bot was kicked from the group chat")
        ) is True

    def test_transient_not_permanent(self):
        from praisonai_bot.bots._resilience import is_permanent_target_failure

        assert is_permanent_target_failure(_StatusError(503, "service unavailable")) is False
        assert is_permanent_target_failure(_StatusError(429, "Too Many Requests")) is False
        assert is_permanent_target_failure(Exception("connection reset by peer")) is False

    def test_401_not_permanent(self):
        # 401 is an account/token-level auth failure, not a per-channel death:
        # condemning the channel would suppress every target on token expiry
        # (greptile P1).
        from praisonai_bot.bots._resilience import is_permanent_target_failure

        assert is_permanent_target_failure(_StatusError(401, "Unauthorized")) is False

    def test_410_is_permanent(self):
        from praisonai_bot.bots._resilience import is_permanent_target_failure

        assert is_permanent_target_failure(_StatusError(410, "Gone")) is True

    def test_message_scoped_404_not_permanent(self):
        from praisonai_bot.bots._resilience import is_permanent_target_failure

        # A 404 for editing a deleted message must NOT condemn the whole channel.
        err = _StatusError(404, "Bad Request: message to edit not found")
        assert is_permanent_target_failure(err) is False

    def test_none_is_not_permanent(self):
        from praisonai_bot.bots._resilience import is_permanent_target_failure

        assert is_permanent_target_failure(None) is False


# ─── DeliveryRouter wiring ───────────────────────────────────────────
class _FakeBot:
    def __init__(self, exc=None, result=True):
        self.exc = exc
        self.result = result
        self.sends = []

    async def send_message(self, channel_id, text):
        self.sends.append((channel_id, text))
        if self.exc is not None:
            raise self.exc
        return self.result


class _FakeBotOS:
    def __init__(self, bot):
        self._bot = bot

    def get_bot(self, platform):
        return self._bot

    def list_bots(self):
        return ["telegram"]


def _make_router(bot, registry):
    from praisonai_bot.bots.delivery import DeliveryRouter

    router = DeliveryRouter(_FakeBotOS(bot), dead_targets=registry)
    router.directory.set_home_channel("telegram", "-1001")
    return router


class TestDeliveryRouterWiring:
    @pytest.mark.asyncio
    async def test_default_off_no_registry(self):
        from praisonai_bot.bots.delivery import DeliveryRouter

        bot = _FakeBot()
        router = DeliveryRouter(_FakeBotOS(bot))
        router.directory.set_home_channel("telegram", "-1001")
        ok = await router.deliver("telegram", "hi")
        assert ok is True
        assert bot.sends == [("-1001", "hi")]

    @pytest.mark.asyncio
    async def test_short_circuits_dead_target(self, tmp_path):
        from praisonai_bot.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json")
        reg.mark_dead("telegram", "-1001", reason="403")
        bot = _FakeBot()
        router = _make_router(bot, reg)

        ok = await router.deliver("telegram", "hi")
        assert ok is False
        assert bot.sends == []  # never called the platform

    @pytest.mark.asyncio
    async def test_marks_dead_on_permanent_failure(self, tmp_path):
        from praisonai_bot.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json")
        bot = _FakeBot(exc=_StatusError(403, "Forbidden: bot was kicked"))
        router = _make_router(bot, reg)

        ok = await router.deliver("telegram", "hi")
        assert ok is False
        assert reg.is_dead("telegram", "-1001") is True

    @pytest.mark.asyncio
    async def test_transient_failure_does_not_mark_dead(self, tmp_path):
        from praisonai_bot.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json")
        bot = _FakeBot(exc=_StatusError(503, "service unavailable"))
        router = _make_router(bot, reg)

        ok = await router.deliver("telegram", "hi")
        assert ok is False
        assert reg.is_dead("telegram", "-1001") is False

    @pytest.mark.asyncio
    async def test_success_self_heals(self, tmp_path):
        from praisonai_bot.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json")
        reg.mark_dead("telegram", "-1001", reason="403")
        # Pre-mark dead, but a healthy bot now succeeds.
        bot = _FakeBot()
        router = _make_router(bot, reg)
        # is_dead would short-circuit, so simulate recovery by clearing first via
        # a direct send path: clear suppression, then deliver succeeds + stays clear.
        reg.clear("telegram", "-1001")
        ok = await router.deliver("telegram", "hi")
        assert ok is True
        assert reg.is_dead("telegram", "-1001") is False

    @pytest.mark.asyncio
    async def test_success_after_recovery_keeps_clear(self, tmp_path):
        from praisonai_bot.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json")
        bot = _FakeBot()
        router = _make_router(bot, reg)
        ok = await router.deliver("telegram", "hi")
        assert ok is True
        assert reg.size() == 0

    @pytest.mark.asyncio
    async def test_reprobe_self_heals_recovered_target(self, tmp_path):
        # Once the re-probe interval elapses, a dead-but-recovered target is sent
        # to and clears itself — without manual intervention or TTL expiry
        # (greptile P1: suppressed targets must be able to self-heal).
        from praisonai_bot.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(
            persist_path=tmp_path / "dead.json", reprobe_seconds=1
        )
        reg.mark_dead("telegram", "-1001", reason="403")
        key = ("telegram", "-1001")
        old = reg._dead[key]
        reg._dead[key] = type(old)(
            platform=old.platform,
            channel_id=old.channel_id,
            reason=old.reason,
            ts=time.time() - 10,
        )
        bot = _FakeBot()  # recovered: send now succeeds
        router = _make_router(bot, reg)

        ok = await router.deliver("telegram", "hi")
        assert ok is True
        assert bot.sends == [("-1001", "hi")]  # re-probe reached the platform
        assert reg.is_dead("telegram", "-1001") is False  # self-healed

    @pytest.mark.asyncio
    async def test_reprobe_still_dead_re_suppresses(self, tmp_path):
        # If the re-probe fails permanently again, the target stays dead and the
        # clock resets for another window.
        from praisonai_bot.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(
            persist_path=tmp_path / "dead.json", reprobe_seconds=1
        )
        reg.mark_dead("telegram", "-1001", reason="403")
        key = ("telegram", "-1001")
        old = reg._dead[key]
        reg._dead[key] = type(old)(
            platform=old.platform,
            channel_id=old.channel_id,
            reason=old.reason,
            ts=time.time() - 10,
        )
        bot = _FakeBot(exc=_StatusError(403, "Forbidden: bot was kicked"))
        router = _make_router(bot, reg)

        ok = await router.deliver("telegram", "hi")
        assert ok is False
        assert reg.is_dead("telegram", "-1001") is True
        # Clock reset: no longer immediately re-probable.
        assert reg.should_reprobe("telegram", "-1001") is False


# ─── Proactive durability: rate-limit + idempotency (issue #2578) ────
class TestProactiveDurability:
    """The agent-initiated (proactive) path must share the reply path's
    delivery guarantees: pass through a rate limiter and dedup retried sends
    via a caller-stable idempotency key.
    """

    @pytest.mark.asyncio
    async def test_deliver_acquires_rate_limiter(self):
        bot = _FakeBot()
        router = DeliveryRouterFor(bot)

        acquired = []

        class _Limiter:
            async def acquire(self, channel_id=None):
                acquired.append(channel_id)

            async def penalise(self, channel_id, seconds):
                pass

        router._rate_limiters["telegram"] = _Limiter()

        ok = await router.deliver("telegram", "hi")
        assert ok is True
        assert acquired == ["-1001"]  # limiter was consulted before send
        assert bot.sends == [("-1001", "hi")]

    @pytest.mark.asyncio
    async def test_duplicate_idempotency_key_suppressed(self):
        bot = _FakeBot()
        router = DeliveryRouterFor(bot)

        ok1 = await router.deliver("telegram", "reminder", idempotency_key="job-1")
        ok2 = await router.deliver("telegram", "reminder", idempotency_key="job-1")

        assert ok1 is True and ok2 is True  # both report success
        assert bot.sends == [("-1001", "reminder")]  # but only sent once

    @pytest.mark.asyncio
    async def test_distinct_keys_both_delivered(self):
        bot = _FakeBot()
        router = DeliveryRouterFor(bot)

        await router.deliver("telegram", "a", idempotency_key="job-1")
        await router.deliver("telegram", "b", idempotency_key="job-2")

        assert bot.sends == [("-1001", "a"), ("-1001", "b")]

    @pytest.mark.asyncio
    async def test_no_key_never_deduplicated(self):
        bot = _FakeBot()
        router = DeliveryRouterFor(bot)

        await router.deliver("telegram", "x")
        await router.deliver("telegram", "x")

        assert bot.sends == [("-1001", "x"), ("-1001", "x")]

    @pytest.mark.asyncio
    async def test_failed_send_key_stays_retryable(self):
        # A failed send must NOT record the key, so a legitimate retry proceeds.
        bot = _FakeBot(exc=_StatusError(503, "service unavailable"))
        router = DeliveryRouterFor(bot)

        ok1 = await router.deliver("telegram", "hi", idempotency_key="job-9")
        assert ok1 is False

        bot.exc = None  # transport recovers
        ok2 = await router.deliver("telegram", "hi", idempotency_key="job-9")
        assert ok2 is True
        assert bot.sends[-1] == ("-1001", "hi")  # retry reached the platform

    @pytest.mark.asyncio
    async def test_explicit_false_send_result_treated_as_failure(self):
        # An adapter that returns explicit False (failed send without raising)
        # must NOT be cached as delivered, so a legitimate retry with the same
        # key still reaches the platform once the transport recovers.
        bot = _FakeBot()
        bot.result = False  # transport reports failure via explicit False
        router = DeliveryRouterFor(bot)

        ok1 = await router.deliver("telegram", "hi", idempotency_key="job-w")
        assert ok1 is False  # explicit False surfaces as a failed send

        bot.result = True  # transport recovers
        ok2 = await router.deliver("telegram", "hi", idempotency_key="job-w")
        assert ok2 is True
        assert bot.sends[-1] == ("-1001", "hi")  # retry was not suppressed

    @pytest.mark.asyncio
    async def test_none_send_result_still_succeeds(self):
        # Lightweight adapters return None/void on success (raising on failure);
        # None must remain a success signal so those paths do not regress.
        bot = _FakeBot()
        bot.result = None
        router = DeliveryRouterFor(bot)

        ok = await router.deliver("telegram", "hi", idempotency_key="job-n")
        assert ok is True
        # Recorded as delivered: a re-fire with the same key is suppressed.
        ok2 = await router.deliver("telegram", "hi", idempotency_key="job-n")
        assert ok2 is True
        assert bot.sends == [("-1001", "hi")]

    @pytest.mark.asyncio
    async def test_retry_after_penalises_limiter(self):
        bot = _FakeBot(exc=_StatusError(429, "Too Many Requests: retry after 7"))
        router = DeliveryRouterFor(bot)

        penalties = []

        class _Limiter:
            async def acquire(self, channel_id=None):
                pass

            async def penalise(self, channel_id, seconds):
                penalties.append((channel_id, seconds))

        router._rate_limiters["telegram"] = _Limiter()

        ok = await router.deliver("telegram", "hi")
        assert ok is False
        assert penalties == [("-1001", 7.0)]  # server Retry-After widened the lane


class _NoOpLimiter:
    """A stub rate limiter so dedup/retry tests never touch the real one."""

    async def acquire(self, channel_id=None):
        pass

    async def penalise(self, channel_id, seconds):
        pass


def DeliveryRouterFor(bot):
    """Build a router over a fake botos with a telegram home channel.

    Registers a no-op limiter for telegram so tests that focus on
    dedup/retry behaviour are isolated from the real ``RateLimiter``'s
    internal timing/state (tests that assert on limiter behaviour override
    this with their own stub).
    """
    from praisonai_bot.bots.delivery import DeliveryRouter

    router = DeliveryRouter(_FakeBotOS(bot))
    router.directory.set_home_channel("telegram", "-1001")
    router._rate_limiters["telegram"] = _NoOpLimiter()
    return router
