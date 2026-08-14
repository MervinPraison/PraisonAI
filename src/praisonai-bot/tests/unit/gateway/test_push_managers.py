"""Tests for push ChannelManager, PresenceManager, and DeliveryGuaranteeManager."""

import asyncio
import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from praisonaiagents.gateway.config import DeliveryConfig, PollingConfig, PresenceConfig
from praisonaiagents.gateway.protocols import EventType, GatewayEvent


# ---------------------------------------------------------------------------
# Helpers — lightweight mock gateway
# ---------------------------------------------------------------------------

class MockGateway:
    """Minimal mock of WebSocketGateway for testing push managers."""

    def __init__(self):
        self._clients = {}
        self._sent: list = []  # (client_id, data)
        self._channel_mgr = None
        self._presence_mgr = None
        self._delivery_mgr = None
        self._redis_pubsub = None

    async def _send_to_client(self, client_id: str, data: dict) -> None:
        self._sent.append((client_id, data))


# ---------------------------------------------------------------------------
# ChannelManager tests
# ---------------------------------------------------------------------------

class TestChannelManager:
    @pytest.fixture
    def gateway(self):
        return MockGateway()

    @pytest.fixture
    def mgr(self, gateway):
        from praisonai_bot.gateway.push_channels import ChannelManager
        cm = ChannelManager(gateway)
        gateway._channel_mgr = cm
        return cm

    def test_add_channel(self, mgr):
        assert mgr.add_channel("alerts") is True
        assert mgr.add_channel("alerts") is False  # duplicate
        assert "alerts" in mgr.list_channels()

    def test_remove_channel(self, mgr):
        mgr.add_channel("temp")
        assert mgr.remove_channel("temp") is True
        assert mgr.remove_channel("temp") is False
        assert "temp" not in mgr.list_channels()

    def test_subscribe_unsubscribe(self, mgr):
        mgr.add_channel("ch1")
        assert mgr.subscribe_client("c1", "ch1") is True
        assert mgr.subscribe_client("c1", "ch1") is False  # already subscribed
        assert "c1" in mgr.get_subscribers("ch1")
        assert "ch1" in mgr.get_client_channels("c1")

        assert mgr.unsubscribe_client("c1", "ch1") is True
        assert mgr.unsubscribe_client("c1", "ch1") is False
        assert "c1" not in mgr.get_subscribers("ch1")

    def test_subscribe_nonexistent_channel(self, mgr):
        assert mgr.subscribe_client("c1", "noexist") is False

    def test_unsubscribe_all(self, mgr):
        mgr.add_channel("a")
        mgr.add_channel("b")
        mgr.subscribe_client("c1", "a")
        mgr.subscribe_client("c1", "b")
        mgr.unsubscribe_all("c1")
        assert mgr.get_client_channels("c1") == []
        assert "c1" not in mgr.get_subscribers("a")
        assert "c1" not in mgr.get_subscribers("b")

    def test_remove_channel_unsubscribes_clients(self, mgr):
        mgr.add_channel("ch")
        mgr.subscribe_client("c1", "ch")
        mgr.subscribe_client("c2", "ch")
        mgr.remove_channel("ch")
        assert mgr.get_client_channels("c1") == []
        assert mgr.get_client_channels("c2") == []

    @pytest.mark.asyncio
    async def test_publish_to_channel(self, mgr, gateway):
        mgr.add_channel("ch")
        mgr.subscribe_client("c1", "ch")
        mgr.subscribe_client("c2", "ch")

        event = GatewayEvent(type=EventType.CHANNEL_MESSAGE, data={"text": "hi"})
        count = await mgr.publish_to_channel("ch", event)
        assert count == 2
        assert len(gateway._sent) == 2

    @pytest.mark.asyncio
    async def test_publish_with_exclude(self, mgr, gateway):
        mgr.add_channel("ch")
        mgr.subscribe_client("c1", "ch")
        mgr.subscribe_client("c2", "ch")

        event = GatewayEvent(type=EventType.CHANNEL_MESSAGE, data={})
        count = await mgr.publish_to_channel("ch", event, exclude=["c1"])
        assert count == 1
        assert gateway._sent[0][0] == "c2"

    @pytest.mark.asyncio
    async def test_publish_to_nonexistent_channel(self, mgr, gateway):
        event = GatewayEvent(type=EventType.CHANNEL_MESSAGE, data={})
        count = await mgr.publish_to_channel("nope", event)
        assert count == 0

    @pytest.mark.asyncio
    async def test_handle_message_subscribe(self, mgr, gateway):
        mgr.add_channel("ch")
        resp = await mgr.handle_message("c1", "channel.subscribe", {"channel": "ch"})
        assert resp["ok"] is True
        assert "c1" in mgr.get_subscribers("ch")

    @pytest.mark.asyncio
    async def test_handle_message_list(self, mgr, gateway):
        mgr.add_channel("a")
        mgr.add_channel("b")
        resp = await mgr.handle_message("c1", "channel.list", {})
        assert set(resp["channels"]) == {"a", "b"}

    def test_get_channel_info(self, mgr):
        mgr.add_channel("info_ch", metadata={"desc": "test"})
        mgr.subscribe_client("c1", "info_ch")
        info = mgr.get_channel("info_ch")
        assert info is not None
        assert info.name == "info_ch"
        assert info.subscriber_count == 1
        assert info.metadata["desc"] == "test"

    def test_get_channel_nonexistent(self, mgr):
        assert mgr.get_channel("nope") is None


# ---------------------------------------------------------------------------
# PresenceManager tests
# ---------------------------------------------------------------------------

class TestPresenceManager:
    @pytest.fixture
    def gateway(self):
        gw = MockGateway()
        # PresenceManager needs a channel_mgr reference for broadcasting
        from praisonai_bot.gateway.push_channels import ChannelManager
        gw._channel_mgr = ChannelManager(gw)
        return gw

    @pytest.fixture
    def mgr(self, gateway):
        from praisonai_bot.gateway.push_presence import PresenceManager
        cfg = PresenceConfig(broadcast_changes=False)  # Disable broadcasts for simpler tests
        pm = PresenceManager(gateway, cfg)
        gateway._presence_mgr = pm
        return pm

    @pytest.mark.asyncio
    async def test_track_and_get_presence(self, mgr):
        await mgr.track_presence("c1", "online", {"name": "Alice"})
        info = mgr.get_presence("c1")
        assert info is not None
        assert info.status == "online"
        assert info.metadata["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_remove_presence(self, mgr):
        await mgr.track_presence("c1")
        await mgr.remove_presence("c1")
        assert mgr.get_presence("c1") is None

    @pytest.mark.asyncio
    async def test_get_all_presence(self, mgr):
        await mgr.track_presence("c1", "online")
        await mgr.track_presence("c2", "idle")
        all_p = mgr.get_all_presence()
        assert len(all_p) == 2

    @pytest.mark.asyncio
    async def test_get_online_count(self, mgr):
        await mgr.track_presence("c1", "online")
        await mgr.track_presence("c2", "offline")
        await mgr.track_presence("c3", "online")
        assert mgr.get_online_count() == 2

    @pytest.mark.asyncio
    async def test_handle_heartbeat(self, mgr):
        resp = await mgr.handle_message("c1", "presence.heartbeat", {"status": "online"})
        assert resp["ok"] is True
        assert mgr.get_presence("c1") is not None

    @pytest.mark.asyncio
    async def test_handle_query(self, mgr):
        await mgr.track_presence("c1", "online")
        resp = await mgr.handle_message("x", "presence.query", {})
        assert resp["type"] == "presence.list"
        assert len(resp["presence"]) == 1


# ---------------------------------------------------------------------------
# DeliveryGuaranteeManager tests
# ---------------------------------------------------------------------------

class TestDeliveryGuaranteeManager:
    @pytest.fixture
    def gateway(self):
        return MockGateway()

    @pytest.fixture
    def mgr(self, gateway):
        from praisonai_bot.gateway.push_delivery import DeliveryGuaranteeManager
        cfg = DeliveryConfig(
            ack_timeout=2, max_retries=2, retry_backoff=1.0, store_backend="memory",
        )
        dm = DeliveryGuaranteeManager(gateway, cfg)
        gateway._delivery_mgr = dm
        return dm

    @pytest.mark.asyncio
    async def test_store_message(self, mgr):
        event = GatewayEvent(type=EventType.CHANNEL_MESSAGE, data={"x": 1})
        eid = await mgr.store_message(event)
        assert eid == event.event_id
        assert eid in mgr._message_store

    @pytest.mark.asyncio
    async def test_track_and_ack(self, mgr):
        event = GatewayEvent(type=EventType.CHANNEL_MESSAGE, data={})
        await mgr.track_delivery("c1", event)

        # Should have pending
        unacked = await mgr.get_unacknowledged("c1")
        assert len(unacked) == 1

        # Acknowledge
        ok = await mgr.acknowledge("c1", event.event_id)
        assert ok is True

        # No more pending
        unacked = await mgr.get_unacknowledged("c1")
        assert len(unacked) == 0

    @pytest.mark.asyncio
    async def test_ack_unknown_returns_false(self, mgr):
        ok = await mgr.acknowledge("c1", "nonexistent")
        assert ok is False

    @pytest.mark.asyncio
    async def test_nack_triggers_immediate_retry(self, mgr):
        event = GatewayEvent(type=EventType.CHANNEL_MESSAGE, data={})
        await mgr.track_delivery("c1", event)
        await mgr.nack("c1", event.event_id)

        # next_retry_at should be <= now
        pending = mgr._pending_acks["c1"][event.event_id]
        assert pending.next_retry_at <= time.time()

    @pytest.mark.asyncio
    async def test_retry_unacknowledged(self, mgr, gateway):
        event = GatewayEvent(type=EventType.CHANNEL_MESSAGE, data={"retry": True})
        await mgr.track_delivery("c1", event)

        count = await mgr.retry_unacknowledged("c1")
        assert count == 1
        assert len(gateway._sent) == 1
        assert gateway._sent[0][1]["_redelivered"] is True

    @pytest.mark.asyncio
    async def test_purge_acknowledged(self, mgr):
        event = GatewayEvent(
            type=EventType.CHANNEL_MESSAGE, data={},
            timestamp=time.time() - 100,
        )
        await mgr.store_message(event)
        purged = await mgr.purge_acknowledged(max_age_seconds=50)
        assert purged == 1
        assert event.event_id not in mgr._message_store

    def test_remove_client(self, mgr):
        mgr._pending_acks["c1"] = {"e1": MagicMock()}
        mgr.remove_client("c1")
        assert "c1" not in mgr._pending_acks

    @pytest.mark.asyncio
    async def test_handle_message_ack(self, mgr):
        event = GatewayEvent(type=EventType.CHANNEL_MESSAGE, data={})
        await mgr.track_delivery("c1", event)
        resp = await mgr.handle_message("c1", "message_ack", {"event_id": event.event_id})
        assert resp["ok"] is True

    @pytest.mark.asyncio
    async def test_handle_message_nack(self, mgr):
        event = GatewayEvent(type=EventType.CHANNEL_MESSAGE, data={})
        await mgr.track_delivery("c1", event)
        resp = await mgr.handle_message("c1", "message_nack", {"event_id": event.event_id})
        assert resp["ok"] is True


# ---------------------------------------------------------------------------
# SQLite durable push-delivery store (Issue #3498)
# ---------------------------------------------------------------------------

class TestSqlitePushStore:
    @pytest.mark.asyncio
    async def test_store_persists_to_sqlite(self, tmp_path):
        from praisonai_bot.gateway.push_delivery import DeliveryGuaranteeManager

        db = tmp_path / "push.sqlite"
        cfg = DeliveryConfig(store_backend="sqlite")
        mgr = DeliveryGuaranteeManager(MockGateway(), cfg, sqlite_path=str(db))
        event = GatewayEvent(type=EventType.CHANNEL_MESSAGE, data={"x": 1})
        await mgr.store_message(event)

        assert db.exists()
        persisted = mgr._sqlite_store.load_all()
        assert any(e.event_id == event.event_id for _cid, e in persisted)

    @pytest.mark.asyncio
    async def test_survives_restart(self, tmp_path):
        """Pending events re-load into a fresh manager after a restart."""
        from praisonai_bot.gateway.push_delivery import DeliveryGuaranteeManager

        db = tmp_path / "push.sqlite"
        cfg = DeliveryConfig(store_backend="sqlite")
        mgr1 = DeliveryGuaranteeManager(MockGateway(), cfg, sqlite_path=str(db))
        event = GatewayEvent(type=EventType.CHANNEL_MESSAGE, data={"y": 2})
        await mgr1.track_delivery("c1", event)

        # Simulate restart: new manager over the same DB file.
        gw2 = MockGateway()
        mgr2 = DeliveryGuaranteeManager(gw2, cfg, sqlite_path=str(db))
        assert event.event_id in mgr2._message_store
        # The recipient's pending-ack state is reconstructed so the event is
        # actually redeliverable (durable at-least-once guarantee).
        unacked = await mgr2.get_unacknowledged("c1")
        assert [e.event_id for e in unacked] == [event.event_id]
        count = await mgr2.retry_unacknowledged("c1")
        assert count == 1
        assert gw2._sent[0][0] == "c1"

    @pytest.mark.asyncio
    async def test_ack_evicts_from_sqlite(self, tmp_path):
        """An acknowledged event is removed from the durable store."""
        from praisonai_bot.gateway.push_delivery import DeliveryGuaranteeManager

        db = tmp_path / "push.sqlite"
        cfg = DeliveryConfig(store_backend="sqlite")
        mgr = DeliveryGuaranteeManager(MockGateway(), cfg, sqlite_path=str(db))
        event = GatewayEvent(type=EventType.CHANNEL_MESSAGE, data={})
        await mgr.track_delivery("c1", event)
        assert mgr._sqlite_store.load_all()  # persisted

        assert await mgr.acknowledge("c1", event.event_id) is True
        assert mgr._sqlite_store.load_all() == []

        # A restart must not resurrect the acked event.
        mgr2 = DeliveryGuaranteeManager(MockGateway(), cfg, sqlite_path=str(db))
        assert event.event_id not in mgr2._message_store
        assert await mgr2.get_unacknowledged("c1") == []

    @pytest.mark.asyncio
    async def test_purge_evicts_from_sqlite(self, tmp_path):
        from praisonai_bot.gateway.push_delivery import DeliveryGuaranteeManager

        db = tmp_path / "push.sqlite"
        cfg = DeliveryConfig(store_backend="sqlite")
        mgr = DeliveryGuaranteeManager(MockGateway(), cfg, sqlite_path=str(db))
        event = GatewayEvent(
            type=EventType.CHANNEL_MESSAGE, data={}, timestamp=time.time() - 100,
        )
        await mgr.store_message(event)
        await mgr.purge_acknowledged(max_age_seconds=50)
        assert mgr._sqlite_store.load_all() == []

    def test_memory_backend_has_no_sqlite_store(self):
        from praisonai_bot.gateway.push_delivery import DeliveryGuaranteeManager

        cfg = DeliveryConfig(store_backend="memory")
        mgr = DeliveryGuaranteeManager(MockGateway(), cfg)
        assert mgr._sqlite_store is None

    def test_default_backend_is_sqlite(self):
        assert DeliveryConfig().store_backend == "sqlite"

    def test_invalid_backend_rejected(self):
        with pytest.raises(ValueError):
            DeliveryConfig(store_backend="postgres")


# ---------------------------------------------------------------------------
# PollManager durability (Issue #3912)
# ---------------------------------------------------------------------------

class TestPollManagerDurability:
    @pytest.fixture
    def gateway(self):
        return MockGateway()

    @pytest.fixture
    def delivery_mgr(self, gateway):
        from praisonai_bot.gateway.push_delivery import DeliveryGuaranteeManager
        cfg = DeliveryConfig(
            ack_timeout=2, max_retries=2, retry_backoff=1.0, store_backend="memory",
        )
        dm = DeliveryGuaranteeManager(gateway, cfg)
        gateway._delivery_mgr = dm
        return dm

    @pytest.fixture
    def poll_mgr(self, gateway):
        from praisonai_bot.gateway.push_polling import PollManager
        return PollManager(gateway, PollingConfig())

    @pytest.mark.asyncio
    async def test_config_bounds_queue_so_overflow_is_reachable(self, gateway):
        """A registered client's queue is bounded by config — overflow (and thus
        durable persistence) is reachable in production, not only via manual test
        override.
        """
        from praisonai_bot.gateway.push_polling import PollManager
        mgr = PollManager(gateway, PollingConfig(max_queue_size=2))
        reg = mgr.register_client(client_id="c1")
        state = mgr.get_client_state(reg["poll_token"])
        assert state.queue.maxsize == 2

    @pytest.mark.asyncio
    async def test_zero_max_queue_size_is_unbounded(self, gateway):
        from praisonai_bot.gateway.push_polling import PollManager
        mgr = PollManager(gateway, PollingConfig(max_queue_size=0))
        reg = mgr.register_client(client_id="c1")
        state = mgr.get_client_state(reg["poll_token"])
        assert state.queue.maxsize == 0

    @pytest.mark.asyncio
    async def test_overflow_persists_to_durable_store(self, poll_mgr, delivery_mgr):
        reg = poll_mgr.register_client(client_id="c1")
        state = poll_mgr.get_client_state(reg["poll_token"])
        # Force a full queue so the next enqueue overflows.
        state.queue = asyncio.Queue(maxsize=1)
        state.queue.put_nowait({"first": True})

        event = GatewayEvent(type=EventType.CHANNEL_MESSAGE, data={"n": 2})
        ok = poll_mgr.enqueue_for_client("c1", event.to_dict())
        # Overflow is a recorded, durable outcome — not a silent drop.
        assert ok is True
        await asyncio.sleep(0)  # let the scheduled track_delivery run

        unacked = await delivery_mgr.get_unacknowledged("c1")
        assert [e.event_id for e in unacked] == [event.event_id]

    @pytest.mark.asyncio
    async def test_overflow_without_store_returns_false(self, poll_mgr, gateway):
        assert getattr(gateway, "_delivery_mgr", None) is None
        reg = poll_mgr.register_client(client_id="c1")
        state = poll_mgr.get_client_state(reg["poll_token"])
        state.queue = asyncio.Queue(maxsize=1)
        state.queue.put_nowait({"first": True})

        ok = poll_mgr.enqueue_for_client(
            "c1", GatewayEvent(type=EventType.CHANNEL_MESSAGE, data={}).to_dict(),
        )
        # No durable backend: an honest False, not a hidden success.
        assert ok is False

    @pytest.mark.asyncio
    async def test_poll_replays_durable_pending(self, poll_mgr, delivery_mgr):
        reg = poll_mgr.register_client(client_id="c1")
        event = GatewayEvent(type=EventType.CHANNEL_MESSAGE, data={"replay": True})
        await delivery_mgr.track_delivery("c1", event)

        msgs = await poll_mgr.poll_messages(reg["poll_token"], timeout=0)
        assert [m["event_id"] for m in msgs] == [event.event_id]

    @pytest.mark.asyncio
    async def test_ack_without_delivery_mgr_is_not_ok(self, poll_mgr, gateway):
        assert getattr(gateway, "_delivery_mgr", None) is None
        routes = {r.path: r for r in poll_mgr.get_routes()}
        ack = routes["/api/push/poll/ack"].endpoint
        reg = poll_mgr.register_client(client_id="c1")

        req = MagicMock()
        req.json = AsyncMock(return_value={
            "poll_token": reg["poll_token"], "event_id": "e1",
        })
        resp = await ack(req)
        assert resp.status_code == 503
        assert json.loads(bytes(resp.body)) == {
            "ok": False, "error": "delivery guarantee not enabled",
        }

    @pytest.mark.asyncio
    async def test_ack_with_delivery_mgr_evicts_pending(self, poll_mgr, delivery_mgr):
        reg = poll_mgr.register_client(client_id="c1")
        event = GatewayEvent(type=EventType.CHANNEL_MESSAGE, data={})
        await delivery_mgr.track_delivery("c1", event)

        routes = {r.path: r for r in poll_mgr.get_routes()}
        ack = routes["/api/push/poll/ack"].endpoint
        req = MagicMock()
        req.json = AsyncMock(return_value={
            "poll_token": reg["poll_token"], "event_id": event.event_id,
        })
        resp = await ack(req)
        assert json.loads(bytes(resp.body)) == {"ok": True}
        assert await delivery_mgr.get_unacknowledged("c1") == []
