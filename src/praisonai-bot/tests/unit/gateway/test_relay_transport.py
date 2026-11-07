"""Issue #6288 — shipped WebSocket ``RelayTransport`` end-to-end.

Runs a real in-process WebSocket *connector* and drives the transport through
handshake, ordered + acked inbound (with a handler that sends outbound, which
must not deadlock), reconnect with redelivery/dedup, dormancy and rejection.
"""

from __future__ import annotations

import asyncio
import json

import pytest

websockets = pytest.importorskip("websockets")

from praisonai_bot.gateway import WebSocketRelayTransport  # noqa: E402
from praisonai_bot.gateway.relay_transport import RelayHandshakeError  # noqa: E402
from praisonaiagents.gateway import (  # noqa: E402
    CapabilityDescriptor,
    GatewayMessage,
    RelayTransport,
    TargetInfo,
)

CAPS = {"max_message_length": 4096, "supports_edit": True}


def _inbound(seq, text):
    msg = GatewayMessage(content=text, sender_id="u1", session_id="c1")
    return json.dumps({"type": "inbound", "seq": seq, "message": msg.to_dict()})


class _Connector:
    """Fake remote connector; records every frame it receives."""

    def __init__(self, token="secret"):
        self.token = token
        self.frames = []
        self.hellos = []
        self.conns = []
        self.server = None

    async def handler(self, ws):
        hello = json.loads(await ws.recv())
        self.hellos.append(hello)
        if hello.get("token") != self.token:
            await ws.send(json.dumps({"type": "error", "message": "bad token"}))
            return
        await ws.send(json.dumps({"type": "welcome", "capabilities": CAPS}))
        self.conns.append(ws)
        async for raw in ws:
            frame = json.loads(raw)
            self.frames.append(frame)
            if frame["type"] == "outbound":
                await ws.send(json.dumps({
                    "type": "result", "id": frame["id"],
                    "result": {"ok": True, "target": "c1", "summary": "sent"},
                }))

    async def __aenter__(self):
        self.server = await websockets.serve(self.handler, "127.0.0.1", 0)
        port = self.server.sockets[0].getsockname()[1]
        self.url = f"ws://127.0.0.1:{port}"
        return self

    async def __aexit__(self, *exc):
        self.server.close()
        await self.server.wait_closed()


async def _until(pred, timeout=5.0):
    for _ in range(int(timeout / 0.02)):
        if pred():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not met")


def test_satisfies_core_protocol():
    assert isinstance(WebSocketRelayTransport(url="ws://x"), RelayTransport)


def test_handshake_ordered_acked_inbound_and_outbound():
    async def run():
        async with _Connector() as c:
            t = WebSocketRelayTransport(c.url, token="secret", platform="telegram")
            seen = []

            async def on_msg(m):
                seen.append(m.content)
                # Reply from inside the handler: must not deadlock the reader.
                r = await t.send_outbound(TargetInfo(target="c1"), m)
                assert r.ok and r.summary == "sent"

            t.set_inbound_handler(on_msg)
            caps = await t.connect()
            assert isinstance(caps, CapabilityDescriptor)
            assert caps.max_message_length == 4096 and caps.supports_edit
            assert c.hellos[0]["platform"] == "telegram"

            for i, text in enumerate(["a", "b", "c"], start=1):
                await c.conns[0].send(_inbound(i, text))
            await _until(lambda: len([f for f in c.frames if f["type"] == "ack"]) == 3)
            assert seen == ["a", "b", "c"]
            acks = [f["seq"] for f in c.frames if f["type"] == "ack"]
            assert acks == [1, 2, 3]
            await t.disconnect()

    asyncio.run(run())


def test_reconnect_resumes_and_dedups_redelivery():
    async def run():
        async with _Connector() as c:
            t = WebSocketRelayTransport(c.url, token="secret")
            seen = []

            async def on_msg(m):
                seen.append(m.content)

            t.set_inbound_handler(on_msg)
            await t.connect()
            await c.conns[0].send(_inbound(1, "a"))
            await _until(lambda: seen == ["a"])
            await c.conns[0].close()  # connection drop

            await _until(lambda: len(c.conns) == 2, timeout=8)
            assert c.hellos[1]["last_seq"] == 1
            # Connector redelivers seq 1 (unsure it was acked) then seq 2.
            await c.conns[1].send(_inbound(1, "a"))
            await c.conns[1].send(_inbound(2, "b"))
            await _until(lambda: seen == ["a", "b"])
            await _until(lambda: any(f.get("seq") == 2 for f in c.frames))
            assert seen == ["a", "b"]
            await t.disconnect()

    asyncio.run(run())


def test_dormant_and_resume_frames():
    async def run():
        async with _Connector() as c:
            t = WebSocketRelayTransport(c.url, token="secret")
            await t.connect()
            await t.go_dormant()
            await t.connect()  # wake: same connection, resume
            await _until(lambda: [f["type"] for f in c.frames] == ["dormant", "resume"])
            assert len(c.conns) == 1
            await t.disconnect()

    asyncio.run(run())


def test_rejected_handshake_raises():
    async def run():
        async with _Connector() as c:
            t = WebSocketRelayTransport(c.url, token="wrong")
            with pytest.raises(RelayHandshakeError, match="bad token"):
                await t.connect()

    asyncio.run(run())


def test_send_outbound_when_disconnected_returns_failure():
    async def run():
        t = WebSocketRelayTransport("ws://127.0.0.1:1", send_timeout=0.1)
        r = await t.send_outbound(
            TargetInfo(target="c1"),
            GatewayMessage(content="x", sender_id="g", session_id="c1"),
        )
        assert r.ok is False

    asyncio.run(run())


def test_failed_handler_is_not_acked_and_is_redelivered():
    async def run():
        async with _Connector() as c:
            t = WebSocketRelayTransport(c.url, token="secret")
            seen, fail = [], [True]

            async def on_msg(m):
                if m.content == "a" and fail[0]:
                    fail[0] = False
                    raise RuntimeError("transient")
                seen.append(m.content)

            t.set_inbound_handler(on_msg)
            await t.connect()
            await c.conns[0].send(_inbound(1, "a"))
            await c.conns[0].send(_inbound(2, "b"))
            # Failure drops the connection so the connector can redeliver.
            await _until(lambda: len(c.conns) == 2, timeout=8)
            assert c.hellos[1]["last_seq"] == 0
            assert not [f for f in c.frames if f["type"] == "ack"]
            await c.conns[1].send(_inbound(1, "a"))
            await c.conns[1].send(_inbound(2, "b"))
            await _until(lambda: seen == ["a", "b"])
            await _until(lambda: [f["seq"] for f in c.frames if f["type"] == "ack"] == [1, 2])
            await t.disconnect()

    asyncio.run(run())


def test_manual_reconnect_after_drop_without_auto_reconnect():
    async def run():
        async with _Connector() as c:
            t = WebSocketRelayTransport(c.url, token="secret", reconnect=False)
            await t.connect()
            await c.conns[0].close()
            await _until(lambda: t._reader.done())
            await t.connect()  # must really reopen, not return stale caps
            assert len(c.conns) == 2
            r = await t.send_outbound(
                TargetInfo(target="c1"),
                GatewayMessage(content="x", sender_id="g", session_id="c1"),
            )
            assert r.ok
            await t.disconnect()

    asyncio.run(run())


def test_stalled_handshake_times_out_and_closes_socket():
    async def run():
        closed = asyncio.Event()

        async def silent(ws):
            await ws.recv()  # read hello, never reply
            await ws.wait_closed()
            closed.set()

        server = await websockets.serve(silent, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            t = WebSocketRelayTransport(f"ws://127.0.0.1:{port}", send_timeout=0.2)
            with pytest.raises(asyncio.TimeoutError):
                await t.connect()
            await asyncio.wait_for(closed.wait(), 5)
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(run())
