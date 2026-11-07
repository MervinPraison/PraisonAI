"""
WebSocket implementation of the core ``RelayTransport`` protocol (Issue #6288).

Lets a gateway behind NAT/a firewall be fronted by a remote *connector* that
holds the platform socket: the gateway dials **out** to the connector, so no
inbound port is needed.

Usage::

    from praisonai.gateway.relay_transport import WebSocketRelayTransport

    bot = Bot("telegram", agent=agent,
              transport=WebSocketRelayTransport(
                  url="wss://relay.example/ws", token="...", platform="telegram"))

Wire protocol (JSON text frames)::

    gateway   -> connector  {"type": "hello", "token", "platform", "last_seq"}
    connector -> gateway    {"type": "welcome", "capabilities": {...}}
                            | {"type": "error", "message": "..."}
    connector -> gateway    {"type": "inbound", "seq": N, "message": {...}}
    gateway   -> connector  {"type": "ack", "seq": N}       # after handling
    gateway   -> connector  {"type": "outbound", "id", "target", "message"}
    connector -> gateway    {"type": "result", "id", "result": {...}}
    gateway   -> connector  {"type": "dormant"} | {"type": "resume"}

Inbound is processed strictly in ``seq`` order and acked only after the
handler returns; the connector redelivers anything unacked after a reconnect
(``last_seq`` tells it where to resume) and duplicates are skipped, so a
reconnect can neither drop nor reorder a message. Reconnection with
exponential backoff is owned here (``RelayAdapter.supervised_inbound=False``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import uuid
from typing import Any, Awaitable, Callable, Dict, Optional

from praisonaiagents.gateway import (
    CapabilityDescriptor,
    DeliveryResult,
    GatewayMessage,
    TargetInfo,
)

logger = logging.getLogger(__name__)


class RelayHandshakeError(Exception):
    """The connector rejected the handshake (bad token, unknown platform)."""


class WebSocketRelayTransport:
    """``RelayTransport`` over a single outbound WebSocket to a connector.

    Args:
        url: Connector WebSocket URL (``ws://`` or ``wss://``).
        token: Shared secret sent in the ``hello`` frame.
        platform: Platform the connector is fronting (e.g. ``"telegram"``).
        reconnect: Reconnect automatically when the connection drops.
        send_timeout: Seconds to wait for an outbound ``result`` frame.
    """

    def __init__(
        self,
        url: str,
        token: str = "",
        platform: str = "",
        reconnect: bool = True,
        send_timeout: float = 30.0,
    ):
        self.url = url
        self.token = token
        self.platform = platform
        self.reconnect = reconnect
        self.send_timeout = send_timeout

        self._ws: Any = None
        self._handler: Optional[Callable[[GatewayMessage], Awaitable[None]]] = None
        self._capabilities: Optional[CapabilityDescriptor] = None
        self._last_seq = 0
        self._dormant = False
        self._closing = False
        self._connected = asyncio.Event()
        self._pending: Dict[str, asyncio.Future] = {}
        self._inbound: "asyncio.Queue[tuple]" = asyncio.Queue()
        self._reader: Optional[asyncio.Task] = None
        self._worker: Optional[asyncio.Task] = None

    # ── RelayTransport protocol ─────────────────────────────────────

    def set_inbound_handler(
        self, handler: Callable[[GatewayMessage], Awaitable[None]]
    ) -> None:
        self._handler = handler

    async def connect(self) -> CapabilityDescriptor:
        """Dial the connector and handshake; resumes if currently dormant."""
        if self._ws is not None and self._capabilities is not None:
            if self._dormant:
                self._dormant = False
                await self._send({"type": "resume"})
            return self._capabilities

        self._closing = False
        await self._open()
        self._reader = asyncio.create_task(self._read_loop())
        self._worker = asyncio.create_task(self._inbound_loop())
        return self._capabilities  # type: ignore[return-value]

    async def send_outbound(
        self, target: TargetInfo, message: GatewayMessage
    ) -> DeliveryResult:
        request_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await asyncio.wait_for(self._connected.wait(), self.send_timeout)
            await self._send({
                "type": "outbound",
                "id": request_id,
                "target": target.as_dict(),
                "message": message.to_dict(),
            })
            result = await asyncio.wait_for(future, self.send_timeout)
        except Exception as exc:
            return DeliveryResult(
                ok=False, target=target.target, summary="relay send failed",
                detail=str(exc) or type(exc).__name__,
            )
        finally:
            self._pending.pop(request_id, None)
        return DeliveryResult(
            ok=bool(result.get("ok", False)),
            target=str(result.get("target", target.target)),
            summary=str(result.get("summary", "")),
            detail=result.get("detail"),
        )

    async def go_dormant(self) -> None:
        """Ask the connector to buffer inbound; the connection stays open."""
        self._dormant = True
        try:
            await self._send({"type": "dormant"})
        except Exception:  # connector will see unacked events on reconnect
            logger.debug("relay: dormant frame not sent", exc_info=True)

    async def disconnect(self) -> None:
        self._closing = True
        self._connected.clear()
        for task in (self._reader, self._worker):
            if task is not None:
                task.cancel()
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                await ws.close()
            except Exception:  # pragma: no cover - defensive
                pass
        self._fail_pending("relay disconnected")
        self._capabilities = None

    # ── Internals ───────────────────────────────────────────────────

    async def _open(self) -> None:
        try:
            import websockets
        except ImportError as exc:  # pragma: no cover - optional dep
            raise ImportError(
                "WebSocketRelayTransport requires websockets. "
                "Install with: pip install 'praisonai-bot[gateway]'"
            ) from exc

        ws = await websockets.connect(self.url)
        await ws.send(json.dumps({
            "type": "hello",
            "token": self.token,
            "platform": self.platform,
            "last_seq": self._last_seq,
        }))
        reply = json.loads(await ws.recv())
        if reply.get("type") != "welcome":
            await ws.close()
            raise RelayHandshakeError(reply.get("message", "handshake rejected"))
        self._capabilities = CapabilityDescriptor.from_dict(reply["capabilities"])
        self._ws = ws
        self._connected.set()
        if self._dormant:
            await self._send({"type": "dormant"})

    async def _send(self, frame: Dict[str, Any]) -> None:
        if self._ws is None:
            raise ConnectionError("relay not connected")
        await self._ws.send(json.dumps(frame))

    async def _read_loop(self) -> None:
        delay = 1.0
        while not self._closing:
            try:
                async for raw in self._ws:
                    delay = 1.0
                    self._dispatch(json.loads(raw))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("relay: connection to %s lost", self.url, exc_info=True)
            self._connected.clear()
            self._fail_pending("relay connection lost")
            if self._closing or not self.reconnect:
                return
            # Reconnect with exponential backoff + jitter. A handshake
            # rejection is terminal: retrying a bad token will never succeed.
            while not self._closing:
                await asyncio.sleep(delay * (1 + random.random() * 0.1))
                delay = min(delay * 2, 60.0)
                try:
                    await self._open()
                    logger.info("relay: reconnected to %s", self.url)
                    break
                except RelayHandshakeError:
                    logger.error("relay: handshake rejected; giving up")
                    return
                except Exception:
                    logger.debug("relay: reconnect failed", exc_info=True)

    def _dispatch(self, frame: Dict[str, Any]) -> None:
        kind = frame.get("type")
        if kind == "inbound":
            self._inbound.put_nowait((int(frame["seq"]), frame.get("message") or {}))
        elif kind == "result":
            future = self._pending.get(frame.get("id", ""))
            if future is not None and not future.done():
                future.set_result(frame.get("result") or {})

    async def _inbound_loop(self) -> None:
        # Separate from the reader so a handler awaiting ``send_outbound``
        # (whose ``result`` frame the reader must deliver) cannot deadlock.
        while True:
            seq, data = await self._inbound.get()
            if seq > self._last_seq:
                if self._handler is not None:
                    try:
                        await self._handler(GatewayMessage.from_dict(data))
                    except Exception:
                        logger.exception("relay: inbound handler failed (seq=%s)", seq)
                self._last_seq = seq
            try:
                await self._send({"type": "ack", "seq": seq})
            except Exception:  # redelivered + deduped after reconnect
                logger.debug("relay: ack for seq=%s not sent", seq, exc_info=True)

    def _fail_pending(self, reason: str) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(ConnectionError(reason))
