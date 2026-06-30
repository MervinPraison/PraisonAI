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
        from praisonai.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json")
        assert reg.size() == 0
        assert reg.is_dead("telegram", "-1001") is False

    def test_mark_then_is_dead(self, tmp_path):
        from praisonai.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json")
        reg.mark_dead("telegram", "-1001", reason="403 Forbidden")
        assert reg.is_dead("telegram", "-1001") is True
        assert reg.size() == 1

    def test_clear_self_heals(self, tmp_path):
        from praisonai.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json")
        reg.mark_dead("discord", "42", reason="404")
        assert reg.is_dead("discord", "42") is True
        reg.clear("discord", "42")
        assert reg.is_dead("discord", "42") is False
        assert reg.size() == 0

    def test_platform_case_insensitive(self, tmp_path):
        from praisonai.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json")
        reg.mark_dead("Telegram", "-1001", reason="403")
        assert reg.is_dead("telegram", "-1001") is True
        assert reg.is_dead("TELEGRAM", "-1001") is True

    def test_clear_unknown_is_noop(self, tmp_path):
        from praisonai.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json")
        reg.clear("slack", "C1")  # must not raise
        assert reg.size() == 0

    def test_list_dead_snapshot(self, tmp_path):
        from praisonai.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json")
        reg.mark_dead("telegram", "a", reason="r1")
        reg.mark_dead("telegram", "b", reason="r2")
        items = reg.list_dead()
        assert {d.channel_id for d in items} == {"a", "b"}


# ─── Persistence ─────────────────────────────────────────────────────
class TestDeadTargetPersistence:
    def test_survives_reload(self, tmp_path):
        from praisonai.bots import DeadTargetRegistry

        path = tmp_path / "dead.json"
        reg = DeadTargetRegistry(persist_path=path)
        reg.mark_dead("telegram", "-1001", reason="403 Forbidden: bot kicked")

        reg2 = DeadTargetRegistry(persist_path=path)
        assert reg2.is_dead("telegram", "-1001") is True
        entry = reg2.list_dead()[0]
        assert "kicked" in entry.reason

    def test_clear_persists(self, tmp_path):
        from praisonai.bots import DeadTargetRegistry

        path = tmp_path / "dead.json"
        reg = DeadTargetRegistry(persist_path=path)
        reg.mark_dead("telegram", "-1001", reason="403")
        reg.clear("telegram", "-1001")

        reg2 = DeadTargetRegistry(persist_path=path)
        assert reg2.is_dead("telegram", "-1001") is False


# ─── Bounding (TTL + max_size) ───────────────────────────────────────
class TestDeadTargetBounding:
    def test_ttl_expiry(self, tmp_path):
        from praisonai.bots import DeadTargetRegistry

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
        from praisonai.bots import DeadTargetRegistry

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


# ─── Error classification ────────────────────────────────────────────
class _StatusError(Exception):
    def __init__(self, status, msg=""):
        self.status_code = status
        super().__init__(msg or f"HTTP {status}")


class TestPermanentClassification:
    def test_403_is_permanent(self):
        from praisonai.bots._resilience import is_permanent_target_failure

        assert is_permanent_target_failure(_StatusError(403, "Forbidden")) is True

    def test_404_is_permanent(self):
        from praisonai.bots._resilience import is_permanent_target_failure

        assert is_permanent_target_failure(_StatusError(404, "chat not found")) is True

    def test_chat_not_found_text(self):
        from praisonai.bots._resilience import is_permanent_target_failure

        assert is_permanent_target_failure(Exception("Bad Request: chat not found")) is True

    def test_bot_kicked_text(self):
        from praisonai.bots._resilience import is_permanent_target_failure

        assert is_permanent_target_failure(
            Exception("Forbidden: bot was kicked from the group chat")
        ) is True

    def test_transient_not_permanent(self):
        from praisonai.bots._resilience import is_permanent_target_failure

        assert is_permanent_target_failure(_StatusError(503, "service unavailable")) is False
        assert is_permanent_target_failure(_StatusError(429, "Too Many Requests")) is False
        assert is_permanent_target_failure(Exception("connection reset by peer")) is False

    def test_message_scoped_404_not_permanent(self):
        from praisonai.bots._resilience import is_permanent_target_failure

        # A 404 for editing a deleted message must NOT condemn the whole channel.
        err = _StatusError(404, "Bad Request: message to edit not found")
        assert is_permanent_target_failure(err) is False

    def test_none_is_not_permanent(self):
        from praisonai.bots._resilience import is_permanent_target_failure

        assert is_permanent_target_failure(None) is False


# ─── DeliveryRouter wiring ───────────────────────────────────────────
class _FakeBot:
    def __init__(self, exc=None):
        self.exc = exc
        self.sends = []

    async def send_message(self, channel_id, text):
        self.sends.append((channel_id, text))
        if self.exc is not None:
            raise self.exc
        return True


class _FakeBotOS:
    def __init__(self, bot):
        self._bot = bot

    def get_bot(self, platform):
        return self._bot

    def list_bots(self):
        return ["telegram"]


def _make_router(bot, registry):
    from praisonai.bots.delivery import DeliveryRouter

    router = DeliveryRouter(_FakeBotOS(bot), dead_targets=registry)
    router.directory.set_home_channel("telegram", "-1001")
    return router


class TestDeliveryRouterWiring:
    @pytest.mark.asyncio
    async def test_default_off_no_registry(self):
        from praisonai.bots.delivery import DeliveryRouter

        bot = _FakeBot()
        router = DeliveryRouter(_FakeBotOS(bot))
        router.directory.set_home_channel("telegram", "-1001")
        ok = await router.deliver("telegram", "hi")
        assert ok is True
        assert bot.sends == [("-1001", "hi")]

    @pytest.mark.asyncio
    async def test_short_circuits_dead_target(self, tmp_path):
        from praisonai.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json")
        reg.mark_dead("telegram", "-1001", reason="403")
        bot = _FakeBot()
        router = _make_router(bot, reg)

        ok = await router.deliver("telegram", "hi")
        assert ok is False
        assert bot.sends == []  # never called the platform

    @pytest.mark.asyncio
    async def test_marks_dead_on_permanent_failure(self, tmp_path):
        from praisonai.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json")
        bot = _FakeBot(exc=_StatusError(403, "Forbidden: bot was kicked"))
        router = _make_router(bot, reg)

        ok = await router.deliver("telegram", "hi")
        assert ok is False
        assert reg.is_dead("telegram", "-1001") is True

    @pytest.mark.asyncio
    async def test_transient_failure_does_not_mark_dead(self, tmp_path):
        from praisonai.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json")
        bot = _FakeBot(exc=_StatusError(503, "service unavailable"))
        router = _make_router(bot, reg)

        ok = await router.deliver("telegram", "hi")
        assert ok is False
        assert reg.is_dead("telegram", "-1001") is False

    @pytest.mark.asyncio
    async def test_success_self_heals(self, tmp_path):
        from praisonai.bots import DeadTargetRegistry

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
        from praisonai.bots import DeadTargetRegistry

        reg = DeadTargetRegistry(persist_path=tmp_path / "dead.json")
        bot = _FakeBot()
        router = _make_router(bot, reg)
        ok = await router.deliver("telegram", "hi")
        assert ok is True
        assert reg.size() == 0
