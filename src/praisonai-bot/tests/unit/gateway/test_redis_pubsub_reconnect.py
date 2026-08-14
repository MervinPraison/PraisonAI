"""Tests for RedisPubSubAdapter reconnect + degraded-state surfacing (Issue #3913).

The adapter must reconnect on a dropped Redis connection, re-subscribe its
channels, record itself as a degraded owner while the outage lasts, clear that
record on recovery, and count publish/presence writes dropped while
disconnected.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from praisonaiagents.gateway.config import RedisConfig
from praisonaiagents.gateway.degraded_state import DegradedCapabilityRegistry
from praisonai_bot.gateway.redis_pubsub import RedisPubSubAdapter


OWNER = (RedisPubSubAdapter._DEGRADED_OWNER_KIND, RedisPubSubAdapter._DEGRADED_OWNER_ID)


def _adapter(registry=None):
    return RedisPubSubAdapter(RedisConfig(host="localhost"), degraded_registry=registry)


class TestDroppedWriteCounting:
    @pytest.mark.asyncio
    async def test_publish_while_disconnected_counts_dropped(self):
        adapter = _adapter()
        assert adapter._client is None
        await adapter.publish("chan", {"a": 1})
        await adapter.set_presence("c1", {"x": 1})
        await adapter.remove_presence("c1")
        await adapter.store_message("e1", {"a": 1})
        await adapter.delete_message("e1")
        assert adapter.dropped_writes == 5


class TestDegradedMarking:
    def test_mark_and_clear_records_into_registry(self):
        registry = DegradedCapabilityRegistry()
        adapter = _adapter(registry)

        adapter._mark_degraded("connection reset")
        assert adapter.is_degraded is True
        owner = registry.find(*OWNER)
        assert owner is not None
        assert owner.owner_kind == "route"
        assert owner.owner_id == "redis-pubsub"
        assert owner.retry_hint  # actionable hint present
        assert "connection reset" in owner.reason

        adapter._clear_degraded()
        assert adapter.is_degraded is False
        assert registry.find(*OWNER) is None

    def test_mark_without_registry_is_safe(self):
        adapter = _adapter(None)
        adapter._mark_degraded("boom")
        assert adapter.is_degraded is True
        adapter._clear_degraded()
        assert adapter.is_degraded is False


class TestReconnect:
    @pytest.mark.asyncio
    async def test_reconnect_resubscribes_channels(self, monkeypatch):
        adapter = _adapter()
        channel_key = adapter._key("channel", "room")
        adapter._subscriptions = {channel_key: AsyncMock()}

        new_pubsub = AsyncMock()

        async def fake_connect():
            adapter._client = AsyncMock()
            adapter._pubsub = new_pubsub

        monkeypatch.setattr(adapter, "connect", fake_connect)

        await adapter._reconnect()

        new_pubsub.subscribe.assert_awaited_once_with(channel_key)

    @pytest.mark.asyncio
    async def test_backoff_returns_true_after_transient_failure(self, monkeypatch):
        adapter = _adapter()
        calls = {"n": 0}

        async def flaky_reconnect():
            calls["n"] += 1
            if calls["n"] < 2:
                raise ConnectionError("still down")

        monkeypatch.setattr(adapter, "_reconnect", flaky_reconnect)

        async def instant_sleep(_delay):
            return None

        monkeypatch.setattr(asyncio, "sleep", instant_sleep)

        recovered = await adapter._reconnect_with_backoff()
        assert recovered is True
        assert calls["n"] == 2

    @pytest.mark.asyncio
    async def test_listener_marks_degraded_then_recovers(self, monkeypatch):
        registry = DegradedCapabilityRegistry()
        adapter = _adapter(registry)

        # First get_message raises (drop), then loop should reconnect and stop.
        pubsub = AsyncMock()
        pubsub.get_message.side_effect = ConnectionError("dropped")
        adapter._pubsub = pubsub

        async def fake_backoff():
            # Simulate a successful reconnect.
            return True

        monkeypatch.setattr(adapter, "_reconnect_with_backoff", fake_backoff)

        # After one reconnect, replace get_message to raise CancelledError so
        # the listener loop terminates cleanly for the test.
        original_backoff = fake_backoff

        async def backoff_then_stop():
            pubsub.get_message.side_effect = asyncio.CancelledError()
            return await original_backoff()

        monkeypatch.setattr(adapter, "_reconnect_with_backoff", backoff_then_stop)

        await adapter._run_listener()

        # Degraded was marked during the outage then cleared on recovery.
        assert adapter.is_degraded is False
        assert registry.find(*OWNER) is None
