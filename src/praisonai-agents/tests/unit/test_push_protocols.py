"""Tests for push notification protocols and dataclasses."""

import time
import pytest

from praisonaiagents.gateway.protocols import (
    ChannelInfo,
    DeliveryGuaranteeProtocol,
    EventType,
    GatewayEvent,
    PresenceInfo,
    PresenceProtocol,
    PushChannelProtocol,
)
from praisonaiagents.gateway.config import (
    DeliveryConfig,
    GatewayConfig,
    PollingConfig,
    PresenceConfig,
    PushConfig,
    RedisConfig,
)


# ---------------------------------------------------------------------------
# EventType additions
# ---------------------------------------------------------------------------


class TestEventTypeAdditions:
    """Verify all new EventType members exist."""

    @pytest.mark.parametrize("name,value", [
        ("CHANNEL_SUBSCRIBE", "channel_subscribe"),
        ("CHANNEL_UNSUBSCRIBE", "channel_unsubscribe"),
        ("CHANNEL_MESSAGE", "channel_message"),
        ("CHANNEL_CREATED", "channel_created"),
        ("CHANNEL_DELETED", "channel_deleted"),
        ("PRESENCE_JOIN", "presence_join"),
        ("PRESENCE_LEAVE", "presence_leave"),
        ("PRESENCE_UPDATE", "presence_update"),
        ("MESSAGE_NACK", "message_nack"),
        ("DELIVERY_RETRY", "delivery_retry"),
        ("POLL_REQUEST", "poll_request"),
        ("POLL_RESPONSE", "poll_response"),
    ])
    def test_event_type_member(self, name, value):
        member = EventType[name]
        assert member.value == value
        assert isinstance(member, str)


# ---------------------------------------------------------------------------
# ChannelInfo
# ---------------------------------------------------------------------------


class TestChannelInfo:
    def test_defaults(self):
        info = ChannelInfo(name="alerts")
        assert info.name == "alerts"
        assert info.subscriber_count == 0
        assert info.metadata == {}
        assert isinstance(info.created_at, float)

    def test_to_dict(self):
        info = ChannelInfo(name="news", metadata={"desc": "breaking"}, subscriber_count=5)
        d = info.to_dict()
        assert d["name"] == "news"
        assert d["subscriber_count"] == 5
        assert d["metadata"]["desc"] == "breaking"

    def test_from_dict_roundtrip(self):
        original = ChannelInfo(name="test", metadata={"k": "v"}, subscriber_count=3)
        d = original.to_dict()
        restored = ChannelInfo.from_dict(d)
        assert restored.name == original.name
        assert restored.metadata == original.metadata
        assert restored.subscriber_count == original.subscriber_count

    def test_from_dict_defaults(self):
        info = ChannelInfo.from_dict({})
        assert info.name == ""
        assert info.subscriber_count == 0


# ---------------------------------------------------------------------------
# PresenceInfo
# ---------------------------------------------------------------------------


class TestPresenceInfo:
    def test_defaults(self):
        info = PresenceInfo(client_id="abc")
        assert info.status == "online"
        assert info.channels == []
        assert info.metadata == {}

    def test_to_dict(self):
        info = PresenceInfo(
            client_id="c1", status="idle",
            metadata={"name": "Alice"}, channels=["ch1"],
        )
        d = info.to_dict()
        assert d["client_id"] == "c1"
        assert d["status"] == "idle"
        assert d["channels"] == ["ch1"]

    def test_from_dict_roundtrip(self):
        original = PresenceInfo(
            client_id="c2", status="offline",
            metadata={"role": "admin"}, channels=["a", "b"],
        )
        d = original.to_dict()
        restored = PresenceInfo.from_dict(d)
        assert restored.client_id == original.client_id
        assert restored.status == original.status
        assert restored.channels == original.channels

    def test_from_dict_defaults(self):
        info = PresenceInfo.from_dict({})
        assert info.client_id == ""
        assert info.status == "online"


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


class TestPushConfig:
    def test_defaults(self):
        cfg = PushConfig()
        assert cfg.enabled is False
        assert cfg.redis is None
        assert cfg.presence.enabled is True
        assert cfg.delivery.enabled is True
        assert cfg.polling.enabled is True

    def test_to_dict(self):
        cfg = PushConfig(enabled=True, redis=RedisConfig())
        d = cfg.to_dict()
        assert d["enabled"] is True
        assert d["redis"] is not None
        assert d["redis"]["host"] == "localhost"

    def test_redis_config_hides_secrets(self):
        cfg = RedisConfig(password="secret123", url="redis://user:pass@host")
        d = cfg.to_dict()
        assert d["password"] == "***"
        assert d["url"] == "***"


class TestGatewayConfigPushField:
    def test_push_field_defaults(self):
        cfg = GatewayConfig()
        assert hasattr(cfg, "push")
        assert cfg.push.enabled is False

    def test_push_in_to_dict(self):
        cfg = GatewayConfig(push=PushConfig(enabled=True))
        d = cfg.to_dict()
        assert "push" in d
        assert d["push"]["enabled"] is True


class TestDeliveryConfig:
    def test_defaults(self):
        cfg = DeliveryConfig()
        assert cfg.ack_timeout == 30
        assert cfg.max_retries == 3
        assert cfg.retry_backoff == 2.0
        assert cfg.message_ttl == 86400
        assert cfg.store_backend == "memory"


class TestPresenceConfigDefaults:
    def test_defaults(self):
        cfg = PresenceConfig()
        assert cfg.heartbeat_interval == 15
        assert cfg.offline_timeout == 45
        assert cfg.broadcast_changes is True


class TestPollingConfig:
    def test_defaults(self):
        cfg = PollingConfig()
        assert cfg.long_poll_timeout == 30
        assert cfg.max_batch_size == 100


# ---------------------------------------------------------------------------
# Protocol structural checks
# ---------------------------------------------------------------------------


class TestProtocolStructure:
    """Verify protocols have the expected methods (structural check)."""

    def test_push_channel_protocol_methods(self):
        expected = {
            "add_channel", "remove_channel", "get_channel", "list_channels",
            "subscribe_client", "unsubscribe_client", "get_subscribers",
            "get_client_channels", "publish_to_channel",
        }
        actual = {
            m for m in dir(PushChannelProtocol)
            if not m.startswith("_")
        }
        assert expected.issubset(actual)

    def test_presence_protocol_methods(self):
        expected = {
            "track_presence", "remove_presence", "get_presence",
            "get_all_presence", "get_online_count",
        }
        actual = {m for m in dir(PresenceProtocol) if not m.startswith("_")}
        assert expected.issubset(actual)

    def test_delivery_guarantee_protocol_methods(self):
        expected = {
            "store_message", "acknowledge", "nack",
            "get_unacknowledged", "retry_unacknowledged", "purge_acknowledged",
        }
        actual = {m for m in dir(DeliveryGuaranteeProtocol) if not m.startswith("_")}
        assert expected.issubset(actual)
