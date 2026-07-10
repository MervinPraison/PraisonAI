"""
RelayAdapter — generic, out-of-process platform-connector adapter (Issue #2485).

Wraps any object satisfying the core ``praisonaiagents.gateway.RelayTransport``
protocol so the gateway can treat an out-of-process platform connector exactly
like an in-process adapter. The platform socket lives in a separate *connector*
process; this adapter:

  * connects + negotiates a :class:`CapabilityDescriptor` at handshake time,
  * receives normalised inbound ``GatewayMessage`` events relayed in and
    dispatches them to registered message handlers,
  * relays outbound sends back down to the connector,
  * goes dormant (without dropping the connection) so scale-to-zero stays
    lossless, since the connector buffers while the gateway sleeps.

This is the *secondary* (wrapper) touch for the relay seam; the contract lives
in core. Heavy/optional transports (WebSocket, gRPC, message bus) implement
``RelayTransport`` and are passed in via ``Bot(transport=...)``.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class RelayAdapter:
    """Adapter that drives an out-of-process platform connection via a relay.

    Args:
        transport: An object satisfying ``praisonaiagents.gateway.RelayTransport``.
        platform: Platform name the remote connector is fronting.
        agent: Agent/AgentTeam/AgentFlow powering responses (optional).
        config: Optional BotConfig override.
    """

    #: The relay transport owns its own out-of-process reconnection and
    #: scale-to-zero dormancy, so the single-``Bot`` supervision wrapper opts
    #: out here rather than double-driving the connection.
    supervised_inbound: bool = False

    def __init__(
        self,
        transport: Any,
        platform: str,
        agent: Optional[Any] = None,
        config: Optional[Any] = None,
    ):
        self._transport = transport
        self._platform = platform
        self._agent = agent
        self._config = config

        self._is_running = False
        self._capabilities: Optional[Any] = None
        self._message_handlers: List[Callable] = []
        self._command_handlers: Dict[str, Callable] = {}

        # A real BotSessionManager so relayed inbound messages are routed to
        # the configured agent exactly like an in-process adapter, and so the
        # owning BotOS can splice the admission gate / identity resolver /
        # delivery router onto ``_session`` (it duck-types on this attribute).
        # Built lazily on ``start`` to keep construction import-light.
        self._session: Optional[Any] = None

    # ── Properties ──────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def platform(self) -> str:
        return self._platform

    @property
    def capabilities(self) -> Optional[Any]:
        """The :class:`CapabilityDescriptor` attested at handshake (post-start)."""
        return self._capabilities

    def set_agent(self, agent: Any) -> None:
        self._agent = agent

    # ── Lifecycle ───────────────────────────────────────────────────

    def _ensure_session(self) -> Any:
        """Build the per-user session manager on first use.

        Mirrors the in-process adapters (``build_session_manager``) so relayed
        inbound traffic gets the same persistent history, durable inbound
        delivery, and—once spliced by ``BotOS``—admission control / identity
        resolution / outbound delivery wiring.
        """
        if self._session is None:
            from praisonaiagents.bots import BotConfig

            from ._session import build_session_manager

            config = self._config or BotConfig(token="")
            self._session = build_session_manager(config, self._platform)
        return self._session

    async def start(self) -> None:
        """Connect the relay, negotiate capabilities, and wire inbound events."""
        if self._is_running:
            logger.warning("RelayAdapter(%s) already running", self._platform)
            return

        self._ensure_session()
        self._transport.set_inbound_handler(self._on_inbound)
        self._capabilities = await self._transport.connect()
        self._is_running = True
        logger.info(
            "RelayAdapter(%s) connected; capabilities=%r",
            self._platform,
            self._capabilities,
        )

    async def stop(self) -> None:
        """Disconnect the relay."""
        if not self._is_running:
            return
        try:
            await self._transport.disconnect()
        finally:
            self._is_running = False

    async def go_dormant(self) -> None:
        """Pause inbound dispatch while keeping the connection alive.

        Delegates to the transport so the connector keeps buffering inbound
        events during scale-to-zero, enabling lossless wake-on-demand.
        """
        go_dormant = getattr(self._transport, "go_dormant", None)
        if go_dormant is not None:
            await go_dormant()

    # ── Inbound ─────────────────────────────────────────────────────

    async def _on_inbound(self, message: Any) -> None:
        """Route a relayed inbound message to the agent, then to handlers.

        The message is first run through the configured agent via the session
        manager (the same path platform adapters take), so a headless gateway
        produces the normal AI reply and honours the spliced admission gate /
        identity / delivery wiring. Any reply is relayed back down through the
        transport. Manually-registered ``on_message`` handlers still fire so
        application-level hooks keep working.
        """
        if self._agent is not None:
            await self._route_to_agent(message)

        for handler in list(self._message_handlers):
            try:
                result = handler(message)
                if isinstance(result, Awaitable):
                    await result
            except Exception:  # pragma: no cover - defensive
                logger.exception(
                    "RelayAdapter(%s) inbound handler failed", self._platform
                )

    async def _route_to_agent(self, message: Any) -> None:
        """Run the inbound message through the agent and relay the reply."""
        session = self._ensure_session()
        content = getattr(message, "content", "")
        prompt = content if isinstance(content, str) else str(content)
        if not prompt:
            return

        user_id = getattr(message, "sender_id", "") or "unknown"
        channel_id = getattr(message, "session_id", "") or user_id
        message_id = getattr(message, "message_id", "") or ""
        reply_to = getattr(message, "reply_to", None)

        try:
            response = await session.chat(
                self._agent,
                user_id,
                prompt,
                chat_id=channel_id,
                message_id=message_id,
            )
        except Exception:
            logger.exception(
                "RelayAdapter(%s) agent run failed", self._platform
            )
            return

        if response:
            try:
                await self.send_message(
                    channel_id, str(response), reply_to=reply_to
                )
            except Exception:  # pragma: no cover - defensive
                logger.exception(
                    "RelayAdapter(%s) outbound relay failed", self._platform
                )

    def on_message(self, handler: Callable) -> Callable:
        """Register an inbound message handler."""
        self._message_handlers.append(handler)
        return handler

    def on_command(self, command: str) -> Callable:
        """Decorator to register a command handler."""

        def decorator(func: Callable) -> Callable:
            self._command_handlers[command] = func
            return func

        return decorator

    # ── Outbound ────────────────────────────────────────────────────

    async def send_message(
        self,
        channel_id: str,
        content: Any,
        reply_to: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> Any:
        """Relay an outbound message down to the connector."""
        from praisonaiagents.gateway import GatewayMessage, TargetInfo

        target = TargetInfo(target=channel_id, platform=self._platform)
        message = GatewayMessage(
            content=content,
            sender_id="gateway",
            session_id=channel_id,
            reply_to=reply_to,
            metadata={"thread_id": thread_id} if thread_id else {},
        )
        return await self._transport.send_outbound(target, message)
