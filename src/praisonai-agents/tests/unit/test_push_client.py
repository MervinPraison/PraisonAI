"""Tests for PushClient with mock transport."""

import asyncio
import json
import pytest

from praisonaiagents.push.models import ChannelMessage
from praisonaiagents.push.client import PushClient


class MockTransport:
    """A mock transport for testing PushClient without network."""

    def __init__(self):
        self.connected = False
        self.sent_messages: list = []
        self._incoming: asyncio.Queue = asyncio.Queue()
        self._closed = False

    @property
    def is_connected(self) -> bool:
        return self.connected

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False
        self._closed = True

    async def send(self, data: dict) -> None:
        self.sent_messages.append(data)

    async def receive(self) -> dict:
        return await self._incoming.get()

    def inject_message(self, data: dict) -> None:
        """Inject a message into the receive queue."""
        self._incoming.put_nowait(data)


# ---------------------------------------------------------------------------
# ChannelMessage model
# ---------------------------------------------------------------------------

class TestChannelMessage:
    def test_from_event_dict(self):
        msg = ChannelMessage.from_event_dict({
            "channel": "alerts",
            "data": {"level": "high"},
            "event_id": "e1",
            "source": "client-x",
        })
        assert msg.channel == "alerts"
        assert msg.data["level"] == "high"
        assert msg.event_id == "e1"
        assert msg.source == "client-x"

    def test_to_dict_roundtrip(self):
        msg = ChannelMessage(channel="ch1", data={"k": "v"}, event_id="id1")
        d = msg.to_dict()
        assert d["channel"] == "ch1"
        assert d["event_id"] == "id1"


# ---------------------------------------------------------------------------
# PushClient unit tests
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_transport():
    return MockTransport()


@pytest.fixture
def client(mock_transport):
    c = PushClient("ws://test:8765/ws", auto_reconnect=False)
    c._transport = mock_transport
    # ``PushClient._send`` checks ``self._transport.is_connected`` (not the
    # internal ``_connected`` flag), so the mock transport must report itself
    # as connected for send-paths to succeed.
    mock_transport.connected = True
    c._connected = True
    return c


class TestPushClientSubscribe:
    @pytest.mark.asyncio
    async def test_subscribe_sends_message(self, client, mock_transport):
        await client.subscribe("alerts")
        assert any(
            m.get("type") == "channel.subscribe" and m.get("channel") == "alerts"
            for m in mock_transport.sent_messages
        )
        assert "alerts" in client._subscribed_channels

    @pytest.mark.asyncio
    async def test_subscribe_with_callback(self, client, mock_transport):
        received = []

        async def cb(msg):
            received.append(msg)

        await client.subscribe("alerts", cb)
        assert "alerts" in client._channel_callbacks
        assert len(client._channel_callbacks["alerts"]) == 1


class TestPushClientUnsubscribe:
    @pytest.mark.asyncio
    async def test_unsubscribe_sends_message(self, client, mock_transport):
        await client.subscribe("alerts")
        await client.unsubscribe("alerts")
        unsub_msgs = [
            m for m in mock_transport.sent_messages
            if m.get("type") == "channel.unsubscribe"
        ]
        assert len(unsub_msgs) == 1
        assert "alerts" not in client._subscribed_channels


class TestPushClientPublish:
    @pytest.mark.asyncio
    async def test_publish_sends_message(self, client, mock_transport):
        await client.publish("alerts", {"msg": "hello"})
        pub_msgs = [
            m for m in mock_transport.sent_messages
            if m.get("type") == "channel.publish"
        ]
        assert len(pub_msgs) == 1
        assert pub_msgs[0]["channel"] == "alerts"
        assert pub_msgs[0]["data"]["msg"] == "hello"


class TestPushClientReceiveLoop:
    @pytest.mark.asyncio
    async def test_channel_message_dispatched(self, client, mock_transport):
        received = []

        async def cb(msg):
            received.append(msg)

        await client.subscribe("alerts", cb)

        # Start receive loop
        task = asyncio.ensure_future(client._receive_loop())

        # Inject a channel message
        mock_transport.inject_message({
            "type": "channel_message",
            "channel": "alerts",
            "data": {"text": "test"},
            "event_id": "ev1",
        })

        # Give the loop time to process
        await asyncio.sleep(0.1)

        # Stop the loop
        client._connected = False
        mock_transport.inject_message({"type": "_shutdown"})  # unblock receive
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert len(received) == 1
        assert received[0].channel == "alerts"
        assert received[0].data["text"] == "test"

    @pytest.mark.asyncio
    async def test_auto_ack_sent(self, client, mock_transport):
        """Verify the client auto-sends message_ack for events with event_id."""
        task = asyncio.ensure_future(client._receive_loop())

        mock_transport.inject_message({
            "type": "channel_message",
            "channel": "ch1",
            "data": {},
            "event_id": "ev-ack-test",
        })

        await asyncio.sleep(0.1)

        client._connected = False
        mock_transport.inject_message({"type": "_shutdown"})
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        ack_msgs = [
            m for m in mock_transport.sent_messages
            if m.get("type") == "message_ack"
        ]
        assert any(m.get("event_id") == "ev-ack-test" for m in ack_msgs)


class TestPushClientEventHandlers:
    @pytest.mark.asyncio
    async def test_on_decorator(self, client, mock_transport):
        received = []

        @client.on("presence.list")
        async def handler(data):
            received.append(data)

        task = asyncio.ensure_future(client._receive_loop())

        mock_transport.inject_message({
            "type": "presence.list",
            "presence": [{"client_id": "c1", "status": "online"}],
        })

        await asyncio.sleep(0.1)
        client._connected = False
        mock_transport.inject_message({"type": "_shutdown"})
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert len(received) == 1


class TestPushClientPresence:
    @pytest.mark.asyncio
    async def test_set_status(self, client, mock_transport):
        await client.set_status("idle", {"reason": "away"})
        hb_msgs = [
            m for m in mock_transport.sent_messages
            if m.get("type") == "presence.heartbeat"
        ]
        assert len(hb_msgs) == 1
        assert hb_msgs[0]["status"] == "idle"
