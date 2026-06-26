"""
Unit tests for gateway broadcast backpressure / slow-consumer protection.

Verifies that:
  * Each client gets a bounded outbound queue (`_ClientConn`).
  * A frame that would exceed the byte / frame ceilings is rejected so the
    caller can evict the slow consumer.
  * A slow / stalled consumer is evicted with a typed `SLOW_CONSUMER` close and
    does not stall delivery to healthy clients on the shared broadcast path.
  * The advertised gateway policy includes the buffered-bytes / queued-frames
    dimensions.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from praisonaiagents.gateway import GatewayCloseCode, GatewayConfig
from praisonai.gateway.server import (
    WebSocketGateway,
    _ClientConn,
    SLOW_CONSUMER_CLOSE_CODE,
)


class _StallingWS:
    """A websocket whose send_json blocks until released (a stalled client)."""

    def __init__(self):
        self.sent = []
        self.closed = False
        self.close_code = None
        self.close_reason = None
        self._gate = asyncio.Event()

    def release(self):
        self._gate.set()

    async def send_json(self, data):
        await self._gate.wait()
        self.sent.append(data)

    async def close(self, code=None, reason=None):
        self.closed = True
        self.close_code = code
        self.close_reason = reason


class _FastWS:
    """A websocket that accepts frames immediately (a healthy client)."""

    def __init__(self):
        self.sent = []
        self.closed = False

    async def send_json(self, data):
        self.sent.append(data)

    async def close(self, code=None, reason=None):
        self.closed = True


@pytest.mark.asyncio
async def test_offer_rejects_when_frame_ceiling_exceeded():
    ws = _StallingWS()
    conn = _ClientConn(ws, "c1", max_buffered_bytes=0, max_queued_frames=2)
    conn.start()
    try:
        # First two frames admitted (the drain task is blocked on the stall).
        assert conn.offer({"n": 1}) is True
        assert conn.offer({"n": 2}) is True
        # Third exceeds the 2-frame ceiling -> rejected (slow consumer).
        assert conn.offer({"n": 3}) is False
    finally:
        ws.release()
        await conn.close()


@pytest.mark.asyncio
async def test_offer_rejects_when_byte_ceiling_exceeded():
    ws = _StallingWS()
    conn = _ClientConn(ws, "c1", max_buffered_bytes=40, max_queued_frames=0)
    conn.start()
    try:
        # First frame always admitted (at least one in-flight allowed).
        assert conn.offer({"payload": "x" * 100}) is True
        # Second would push buffered_bytes over the 40-byte ceiling.
        assert conn.offer({"payload": "y" * 100}) is False
    finally:
        ws.release()
        await conn.close()


@pytest.mark.asyncio
async def test_offer_unbounded_when_disabled():
    ws = _StallingWS()
    conn = _ClientConn(ws, "c1", max_buffered_bytes=0, max_queued_frames=0)
    conn.start()
    try:
        for i in range(50):
            assert conn.offer({"n": i}) is True
    finally:
        ws.release()
        await conn.close()


@pytest.mark.asyncio
async def test_healthy_client_drains_frames():
    ws = _FastWS()
    conn = _ClientConn(ws, "c1", max_buffered_bytes=1_000_000, max_queued_frames=100)
    conn.start()
    try:
        assert conn.offer({"hello": "world"}) is True
        # Give the drain task a chance to run.
        for _ in range(10):
            await asyncio.sleep(0)
            if ws.sent:
                break
        assert ws.sent == [{"hello": "world"}]
        assert conn.buffered_bytes == 0
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_broadcast_evicts_slow_consumer_without_stalling_healthy():
    gateway = WebSocketGateway(
        config=GatewayConfig(max_buffered_bytes=0, max_queued_frames=1)
    )
    slow_ws = _StallingWS()
    fast_ws = _FastWS()
    gateway.add_client("slow", slow_ws)
    gateway.add_client("fast", fast_ws)

    from praisonaiagents.gateway import GatewayEvent, EventType

    # Saturate the slow client's 1-frame queue so the next offer overflows.
    gateway._client_conns["slow"].offer({"prime": True})

    await gateway.broadcast(GatewayEvent(type=EventType.BROADCAST, data={"x": 1}))

    # Slow consumer evicted with a typed SLOW_CONSUMER close; healthy untouched.
    assert "slow" not in gateway._clients
    assert slow_ws.closed is True
    assert slow_ws.close_code == SLOW_CONSUMER_CLOSE_CODE
    assert slow_ws.close_reason == GatewayCloseCode.SLOW_CONSUMER.value
    assert "fast" in gateway._clients

    # Healthy client receives the broadcast frame.
    for _ in range(10):
        await asyncio.sleep(0)
        if fast_ws.sent:
            break
    assert any(f.get("data") == {"x": 1} for f in fast_ws.sent)

    slow_ws.release()
    await gateway._teardown_client_conn("fast")


def test_policy_advertises_buffer_dimensions():
    config = GatewayConfig(max_buffered_bytes=2048, max_queued_frames=7)
    assert config.to_dict()["max_buffered_bytes"] == 2048
    assert config.to_dict()["max_queued_frames"] == 7


def test_config_rejects_negative_queued_frames():
    with pytest.raises(ValueError):
        GatewayConfig(max_queued_frames=-1)


def test_close_code_enum_value():
    assert GatewayCloseCode.SLOW_CONSUMER.value == "slow_consumer"
