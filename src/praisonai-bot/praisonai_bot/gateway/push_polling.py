"""
Push Polling Fallback for PraisonAI Gateway.

Provides HTTP long-polling endpoints for clients that cannot maintain
WebSocket connections.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from praisonaiagents.gateway.config import PollingConfig
from praisonaiagents.gateway.protocols import GatewayEvent

if TYPE_CHECKING:
    from .server import WebSocketGateway

logger = logging.getLogger(__name__)


@dataclass
class PollClientState:
    """Internal state for a registered polling client."""

    client_id: str
    poll_token: str
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    last_poll_at: float = field(default_factory=time.time)
    channels: list = field(default_factory=list)


class PollManager:
    """Manages HTTP long-polling clients.

    Polling clients register to get a token, then poll for messages.
    Messages are queued per-client and delivered in batches.
    """

    def __init__(
        self,
        gateway: "WebSocketGateway",
        config: PollingConfig,
    ) -> None:
        self._gateway = gateway
        self._config = config
        # poll_token -> PollClientState
        self._poll_clients: Dict[str, PollClientState] = {}
        # client_id -> poll_token (reverse lookup)
        self._client_tokens: Dict[str, str] = {}
        self._cleanup_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_cleanup(self) -> None:
        """Start the stale poll client cleanup task."""
        self._cleanup_task = asyncio.ensure_future(self._run_cleanup())

    async def stop_cleanup(self) -> None:
        """Stop cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        self._cleanup_task = None

    # ------------------------------------------------------------------
    # Client registration
    # ------------------------------------------------------------------

    def register_client(
        self, client_id: Optional[str] = None, auth_token: Optional[str] = None,
    ) -> Dict[str, str]:
        """Register a polling client and return a poll token."""
        cid = client_id or str(uuid.uuid4())
        token = str(uuid.uuid4())
        state = PollClientState(client_id=cid, poll_token=token)
        self._poll_clients[token] = state
        self._client_tokens[cid] = token
        logger.debug("Poll client registered: %s", cid)
        return {"client_id": cid, "poll_token": token}

    def deregister_client(self, poll_token: str) -> bool:
        """Remove a polling client."""
        state = self._poll_clients.pop(poll_token, None)
        if state:
            self._client_tokens.pop(state.client_id, None)
            return True
        return False

    def get_client_state(self, poll_token: str) -> Optional[PollClientState]:
        """Get client state by poll token."""
        return self._poll_clients.get(poll_token)

    # ------------------------------------------------------------------
    # Message delivery (called by ChannelManager)
    # ------------------------------------------------------------------

    def enqueue_for_client(self, client_id: str, event_dict: Dict[str, Any]) -> bool:
        """Queue a message for a polling client."""
        token = self._client_tokens.get(client_id)
        if token is None:
            return False
        state = self._poll_clients.get(token)
        if state is None:
            return False
        try:
            state.queue.put_nowait(event_dict)
            return True
        except asyncio.QueueFull:
            logger.warning("Poll queue full for client %s", client_id)
            return False

    # ------------------------------------------------------------------
    # Long-polling
    # ------------------------------------------------------------------

    async def poll_messages(
        self,
        poll_token: str,
        timeout: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Long-poll for messages. Blocks up to timeout seconds."""
        state = self._poll_clients.get(poll_token)
        if state is None:
            return []

        state.last_poll_at = time.time()
        poll_timeout = timeout or self._config.long_poll_timeout
        messages: List[Dict[str, Any]] = []

        # Drain any immediately available messages
        while not state.queue.empty() and len(messages) < self._config.max_batch_size:
            try:
                msg = state.queue.get_nowait()
                messages.append(msg)
            except asyncio.QueueEmpty:
                break

        # If nothing available, wait for the first message or timeout
        if not messages:
            try:
                msg = await asyncio.wait_for(
                    state.queue.get(), timeout=poll_timeout,
                )
                messages.append(msg)
                # Drain any additional messages that arrived
                while (
                    not state.queue.empty()
                    and len(messages) < self._config.max_batch_size
                ):
                    try:
                        messages.append(state.queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break
            except asyncio.TimeoutError:
                pass  # Return empty — client should poll again

        return messages

    # ------------------------------------------------------------------
    # HTTP route handlers (Starlette)
    # ------------------------------------------------------------------

    def get_routes(self) -> list:
        """Return Starlette Route objects for polling endpoints."""
        try:
            from starlette.requests import Request
            from starlette.responses import JSONResponse
            from starlette.routing import Route
        except ImportError:
            logger.warning("starlette not available, polling routes disabled")
            return []

        async def register(request: Request) -> JSONResponse:
            body = await request.json()
            result = self.register_client(
                client_id=body.get("client_id"),
                auth_token=body.get("auth_token"),
            )
            return JSONResponse(result)

        async def messages(request: Request) -> JSONResponse:
            body = await request.json()
            token = body.get("poll_token", "")
            timeout = body.get("timeout")
            msgs = await self.poll_messages(token, timeout)
            return JSONResponse({
                "messages": msgs,
                "poll_interval_hint": self._config.long_poll_timeout,
            })

        async def ack(request: Request) -> JSONResponse:
            body = await request.json()
            token = body.get("poll_token", "")
            event_id = body.get("event_id", "")
            state = self.get_client_state(token)
            if state is None:
                return JSONResponse({"ok": False, "error": "unknown client"}, status_code=404)
            delivery_mgr = getattr(self._gateway, "_delivery_mgr", None)
            if delivery_mgr:
                ok = await delivery_mgr.acknowledge(state.client_id, event_id)
            else:
                ok = True
            return JSONResponse({"ok": ok})

        async def subscribe(request: Request) -> JSONResponse:
            body = await request.json()
            token = body.get("poll_token", "")
            channel = body.get("channel", "")
            state = self.get_client_state(token)
            if state is None:
                return JSONResponse({"ok": False, "error": "unknown client"}, status_code=404)
            channel_mgr = getattr(self._gateway, "_channel_mgr", None)
            if channel_mgr:
                ok = channel_mgr.subscribe_client(state.client_id, channel)
                if ok:
                    state.channels.append(channel)
            else:
                ok = False
            return JSONResponse({"ok": ok, "channel": channel})

        async def unsubscribe(request: Request) -> JSONResponse:
            body = await request.json()
            token = body.get("poll_token", "")
            channel = body.get("channel", "")
            state = self.get_client_state(token)
            if state is None:
                return JSONResponse({"ok": False, "error": "unknown client"}, status_code=404)
            channel_mgr = getattr(self._gateway, "_channel_mgr", None)
            if channel_mgr:
                ok = channel_mgr.unsubscribe_client(state.client_id, channel)
                if ok and channel in state.channels:
                    state.channels.remove(channel)
            else:
                ok = False
            return JSONResponse({"ok": ok, "channel": channel})

        async def presence(request: Request) -> JSONResponse:
            channel = request.query_params.get("channel")
            presence_mgr = getattr(self._gateway, "_presence_mgr", None)
            if presence_mgr:
                entries = presence_mgr.get_all_presence(channel)
                return JSONResponse({
                    "presence": [p.to_dict() for p in entries],
                })
            return JSONResponse({"presence": []})

        async def heartbeat(request: Request) -> JSONResponse:
            body = await request.json()
            token = body.get("poll_token", "")
            state = self.get_client_state(token)
            if state is None:
                return JSONResponse({"ok": False, "error": "unknown client"}, status_code=404)
            state.last_poll_at = time.time()
            presence_mgr = getattr(self._gateway, "_presence_mgr", None)
            if presence_mgr:
                await presence_mgr.track_presence(
                    state.client_id,
                    status=body.get("status", "online"),
                    metadata=body.get("metadata"),
                )
            return JSONResponse({"ok": True})

        return [
            Route("/api/push/poll/register", register, methods=["POST"]),
            Route("/api/push/poll/messages", messages, methods=["POST"]),
            Route("/api/push/poll/ack", ack, methods=["POST"]),
            Route("/api/push/poll/subscribe", subscribe, methods=["POST"]),
            Route("/api/push/poll/unsubscribe", unsubscribe, methods=["POST"]),
            Route("/api/push/poll/presence", presence, methods=["GET"]),
            Route("/api/push/poll/heartbeat", heartbeat, methods=["POST"]),
        ]

    # ------------------------------------------------------------------
    # Internal cleanup
    # ------------------------------------------------------------------

    async def _run_cleanup(self) -> None:
        """Remove stale poll clients."""
        stale_threshold = self._config.long_poll_timeout * 2
        while True:
            try:
                await asyncio.sleep(stale_threshold)
                now = time.time()
                stale_tokens = [
                    token
                    for token, state in self._poll_clients.items()
                    if now - state.last_poll_at > stale_threshold
                ]
                for token in stale_tokens:
                    self.deregister_client(token)
                    logger.debug("Stale poll client removed: %s", token)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Poll cleanup error: %s", e)
