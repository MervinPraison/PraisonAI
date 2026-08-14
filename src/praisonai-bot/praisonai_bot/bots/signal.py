"""
Signal Bot implementation for PraisonAI.

Connects an agent to the end-to-end-encrypted Signal messenger through a
locally-run `signal-cli-rest-api <https://github.com/bbernhard/signal-cli-rest-api>`_
bridge — the same linked-device / bridge connection model already used by the
WhatsApp Web adapter (:mod:`praisonai_bot.bots._whatsapp_web_adapter`). No cloud
bot token is required: the operator links a device to their own Signal account
and points the adapter at the bridge URL.

The adapter talks HTTP/JSON to the bridge (``aiohttp`` is lazy-imported so it
adds no import-time weight) and inherits the shared durability machinery —
outbox/DLQ retry, sessions, commands, and hooks — from the common mixins, so a
Signal channel behaves like every other channel with only a few lines of config.

Usage:
    bot = SignalBot(
        account="+15551234567",
        bridge_url="http://localhost:8080",
        agent=agent,
    )
    await bot.start()
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from praisonaiagents import Agent

from praisonai_bot.bots._protocol_mixin import ChatCommandMixin, MessageHookMixin
from praisonaiagents.bots import (
    BotConfig,
    BotMessage,
    BotUser,
    BotChannel,
    MessageType,
)
from praisonaiagents.bots.protocols import ChannelField, PlatformCapabilities

from ._commands import format_status, format_help, handle_stop_command
from ._failure import failure_reply_text
from ._rate_limit import RateLimiter
from ._ack import AckReactor
from ._outbound_resilience import OutboundResilienceMixin

logger = logging.getLogger(__name__)


class SignalDescriptor:
    """Self-description for the Signal channel (config keys + prompt hint).

    Declared so the gateway config schema, onboarding wizard, and agent prompt
    wire Signal as a first-class channel with zero core edits (see
    :class:`praisonaiagents.bots.protocols.ChannelDescriptor`).
    """

    config_fields = [
        ChannelField(
            name="account",
            required=True,
            prompt="Your linked Signal phone number (e.g. +15551234567)",
            env="SIGNAL_ACCOUNT",
        ),
        ChannelField(
            name="bridge_url",
            required=False,
            prompt="signal-cli-rest-api base URL (default http://localhost:8080)",
            env="SIGNAL_BRIDGE_URL",
        ),
    ]
    system_prompt_hint = (
        "You are replying on Signal, an end-to-end-encrypted messenger: keep "
        "replies plain text; message editing is not available."
    )


class SignalBot(OutboundResilienceMixin, ChatCommandMixin, MessageHookMixin):
    """Signal bot runtime for PraisonAI agents (via a signal-cli-rest-api bridge).

    Example:
        from praisonai_bot.bots import SignalBot
        from praisonaiagents import Agent

        agent = Agent(name="assistant")
        bot = SignalBot(
            account="+15551234567",
            bridge_url="http://localhost:8080",
            agent=agent,
        )
        await bot.start()
    """

    _outbound_platform = "signal"

    channel_descriptor = SignalDescriptor()

    def __init__(
        self,
        token: str = "",
        account: str = "",
        bridge_url: str = "",
        agent: Optional["Agent"] = None,
        config: Optional[BotConfig] = None,
        allowed_users: Optional[List[str]] = None,
        poll_interval: float = 1.0,
        **kwargs,
    ):
        # ``token`` is accepted for parity with the generic Bot adapter wiring
        # (which always passes it); Signal is token-free, so it is unused.
        self._extra_kwargs = kwargs
        self._account = account or os.environ.get("SIGNAL_ACCOUNT", "")
        self._bridge_url = (
            bridge_url or os.environ.get("SIGNAL_BRIDGE_URL", "") or "http://localhost:8080"
        ).rstrip("/")
        self._agent = agent
        self.config = config or BotConfig(token="", mode="polling")
        self._allow_silence = getattr(self.config, "allow_silence", False)
        self._poll_interval = max(0.2, float(poll_interval))

        # DM allowlist (normalised to digits so "+1 555" and "1555" match).
        self._allowed_users: set[str] = set()
        for u in allowed_users or []:
            digits = "".join(c for c in u if c.isdigit())
            if digits:
                self._allowed_users.add(digits)

        self._is_running = False
        self._started_at: Optional[float] = None
        self._bot_user: Optional[BotUser] = None

        from ._session import build_session_manager
        # Exposed as ``_session`` (not ``_session_mgr``) so the gateway routing
        # handler can stage per-route tool policies on it (Issue #2298): that
        # handler looks up ``_session`` before the adapter's own ``chat()``.
        self._session = build_session_manager(self.config, platform="signal")
        self._message_handlers: List[Callable] = []
        self._http_session: Any = None
        self._background_tasks: set = set()
        self._rate_limiter = RateLimiter.for_platform("signal")
        self._ack: AckReactor = AckReactor(
            ack_emoji=self.config.ack_emoji,
            done_emoji=self.config.done_emoji,
        )

        self._command_handlers: Dict[str, Callable] = {}
        self._command_info: Dict[str, Dict[str, Any]] = {}
        self._register_builtins()

    # ── Capabilities ────────────────────────────────────────────────

    @classmethod
    def default_capabilities(cls) -> PlatformCapabilities:
        """Honest capability declaration so shared engines degrade correctly.

        Signal supports typing indicators but not live message editing, so
        streaming falls back to chunked sends rather than in-place edits.
        """
        return PlatformCapabilities(
            max_message_length=2000,
            supports_edit=False,
            supports_typing=True,
            needs_rate_limit=True,
            accepts_webhooks=False,
            supports_media=False,
        )

    def _register_builtins(self) -> None:
        """Register built-in /status, /new, /help, /stop commands."""

        async def _status(msg):
            return format_status(self._agent, "signal", self._started_at, self._is_running)

        async def _new(msg):
            user_id = msg.sender.user_id if msg.sender else "unknown"
            self._session.reset(user_id)
            return "Session reset. Send a message to start a new conversation."

        async def _help(msg):
            extra = {
                name: info.get("description", "")
                for name, info in self._command_info.items()
                if name not in ("status", "new", "help", "stop")
            }
            return format_help(self._agent, "signal", extra or None)

        async def _stop(msg):
            user_id = msg.sender.user_id if msg.sender else "unknown"
            return handle_stop_command(self._session, user_id)

        self.register_command("status", _status, description="Show bot status and info")
        self.register_command("new", _new, description="Reset conversation session")
        self.register_command("help", _help, description="Show this help message")
        self.register_command("stop", _stop, description="Cancel the current agent run")

    # ── Properties ──────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def platform(self) -> str:
        return "signal"

    @property
    def bot_user(self) -> Optional[BotUser]:
        return self._bot_user

    # ── Agent management ────────────────────────────────────────────

    def set_agent(self, agent: "Agent") -> None:
        self._agent = agent

    def get_agent(self) -> Optional["Agent"]:
        return self._agent

    # ── Message handlers ────────────────────────────────────────────

    def on_message(self, handler: Callable) -> Callable:
        self._message_handlers.append(handler)
        return handler

    def on_command(self, command: str) -> Callable:
        def decorator(func: Callable) -> Callable:
            self.register_command(command, func)
            return func
        return decorator

    # ── Lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        """Start polling the signal-cli-rest-api bridge for messages."""
        try:
            import aiohttp
        except ImportError:
            raise ImportError(
                "aiohttp is required for the Signal bot. Install with: pip install aiohttp"
            )
        if not self._account:
            raise ValueError(
                "Signal account is required (set channels.signal.account or SIGNAL_ACCOUNT)."
            )

        self._http_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        self._is_running = True
        self._started_at = time.time()
        self._bot_user = BotUser(
            user_id=self._account,
            username="signal_bot",
            display_name="Signal Bot",
            is_bot=True,
        )
        logger.info("Signal bot polling %s for account %s", self._bridge_url, self._account)

        try:
            while self._is_running:
                try:
                    await self._poll_once()
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001 — a poll error must not kill the loop
                    logger.warning("Signal poll error: %s", e)
                await asyncio.sleep(self._poll_interval)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the bot and release the HTTP session."""
        self._is_running = False
        for task in self._background_tasks:
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()
        if self._http_session:
            await self._http_session.close()
            self._http_session = None
        logger.info("Signal bot stopped")

    # ── Receiving ───────────────────────────────────────────────────

    async def _poll_once(self) -> None:
        """Fetch and dispatch any pending messages from the bridge."""
        import aiohttp

        url = f"{self._bridge_url}/v1/receive/{self._account}"
        try:
            async with self._http_session.get(
                url, timeout=aiohttp.ClientTimeout(total=self._poll_interval + 30)
            ) as resp:
                if resp.status != 200:
                    logger.debug("Signal receive returned HTTP %s", resp.status)
                    return
                envelopes = await resp.json()
        except Exception as e:  # noqa: BLE001 — surfaced by caller as a poll error
            logger.debug("Signal receive request failed: %s", e)
            return

        if not isinstance(envelopes, list):
            return
        self._note_inbound()
        for item in envelopes:
            try:
                await self._handle_envelope(item)
            except Exception as e:  # noqa: BLE001 — one bad message must not stop the batch
                logger.warning("Signal message processing error: %s", e)

    async def _handle_envelope(self, item: Dict[str, Any]) -> None:
        """Parse one signal-cli envelope and route it to the agent."""
        envelope = item.get("envelope", item) if isinstance(item, dict) else {}
        data_msg = envelope.get("dataMessage") or {}
        content = data_msg.get("message")
        if not content:
            return  # receipts, typing, empty — nothing to answer

        source = str(envelope.get("source") or envelope.get("sourceNumber") or "")
        source_name = envelope.get("sourceName") or (source or "unknown")
        timestamp_ms = envelope.get("timestamp") or data_msg.get("timestamp") or 0
        try:
            timestamp = float(timestamp_ms) / 1000.0 if timestamp_ms else time.time()
        except (TypeError, ValueError):
            timestamp = time.time()

        group_info = data_msg.get("groupInfo") or {}
        group_id = group_info.get("groupId") or ""
        is_group = bool(group_id)
        chat_id = group_id if is_group else source

        # DM allowlist (groups pass through — group membership is the gate there).
        if self._allowed_users and not is_group:
            sender_digits = "".join(c for c in source if c.isdigit())
            if sender_digits not in self._allowed_users:
                logger.debug("Signal: sender %s not in allowlist", source)
                return

        sender = BotUser(
            user_id=source,
            username=source or source_name,
            display_name=source_name,
            is_bot=False,
        )
        channel = BotChannel(
            channel_id=chat_id,
            name=f"signal:{chat_id}",
            channel_type="group" if is_group else "dm",
        )
        bot_message = BotMessage(
            message_id=str(timestamp_ms) or "",
            content=content,
            message_type=MessageType.TEXT,
            sender=sender,
            channel=channel,
            timestamp=timestamp,
        )

        decision = self.fire_message_received(bot_message)
        if decision.get("drop"):
            logger.debug("Signal message dropped by MESSAGE_RECEIVED hook")
            return
        content = decision.get("content", content)

        for handler in self._message_handlers:
            try:
                await handler(bot_message)
            except Exception as e:  # noqa: BLE001
                logger.error("Signal message handler error: %s", e)

        text = content.strip()
        if text.startswith("/"):
            cmd_name = text.split()[0][1:].lower()
            cmd_handler = self._command_handlers.get(cmd_name)
            if cmd_handler:
                try:
                    response = await cmd_handler(bot_message)
                    if response:
                        await self.send_message(chat_id, response, group=is_group)
                except Exception as e:  # noqa: BLE001
                    logger.error("Signal command '%s' error: %s", cmd_name, e)
                    await self.send_message(chat_id, f"Error: {e}", group=is_group)
                return

        if self._agent and content:
            try:
                response = await self._session.chat(
                    self._agent, source, content,
                    chat_id=chat_id,
                    user_name=source_name or "",
                    message_id=bot_message.message_id,
                    account=getattr(self.config, "account", "default"),
                )
                if response:
                    send_result = self.fire_message_sending(chat_id, str(response))
                    if not send_result["cancel"]:
                        await self.send_message(chat_id, send_result["content"], group=is_group)
                        self.fire_message_sent(chat_id, send_result["content"])
            except Exception as e:  # noqa: BLE001
                logger.error("Signal agent chat error: %s", e)
                await self.send_message(chat_id, failure_reply_text(e), group=is_group)

    # ── Sending ─────────────────────────────────────────────────────

    async def send_message(
        self,
        to: str,
        content: Union[str, Dict[str, Any]],
        reply_to: Optional[str] = None,
        thread_id: Optional[str] = None,
        group: bool = False,
    ) -> BotMessage:
        """Send a text message via the signal-cli-rest-api bridge."""
        import aiohttp

        text = content if isinstance(content, str) else str(content)
        max_len = self.config.max_message_length
        chunks = [text[i:i + max_len] for i in range(0, len(text), max_len)] or [""]

        sent_msg = None
        url = f"{self._bridge_url}/v2/send"
        for chunk in chunks:
            payload: Dict[str, Any] = {
                "number": self._account,
                "message": chunk,
                "recipients": [to],
            }
            await self._rate_limiter.acquire(to)

            async def _post(chunk_text: str = chunk, body: Dict[str, Any] = payload) -> dict:
                async with self._http_session.post(
                    url, json=body, timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status >= 400:
                        detail = await resp.text()
                        raise RuntimeError(
                            f"Signal send error: HTTP {resp.status}: {detail[:200]}"
                        )
                    try:
                        return await resp.json()
                    except Exception:  # noqa: BLE001 — bridge may return empty body
                        return {}

            result = await self.deliver_outbound(
                _post,
                channel_id=to,
                reply_text=chunk,
                reply_to=reply_to,
            )
            msg_id = ""
            if isinstance(result, dict):
                msg_id = str(result.get("timestamp", "") or "")
            sent_msg = BotMessage(
                message_id=msg_id,
                content=chunk,
                message_type=MessageType.TEXT,
                sender=self._bot_user,
                channel=BotChannel(
                    channel_id=to, channel_type="group" if group else "dm"
                ),
            )

        return sent_msg or BotMessage(content=text)

    async def send_typing(self, channel_id: str) -> None:
        """Signal supports typing indicators via the bridge (best-effort)."""
        if not self._http_session:
            return
        import aiohttp

        url = f"{self._bridge_url}/v1/typing-indicator/{self._account}"
        try:
            async with self._http_session.put(
                url, json={"recipient": channel_id},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                await resp.read()
        except Exception as e:  # noqa: BLE001 — typing is cosmetic, never fatal
            logger.debug("Signal typing indicator failed: %s", e)

    async def edit_message(
        self, channel_id: str, message_id: str, content: Union[str, Dict[str, Any]]
    ) -> BotMessage:
        """Signal has no message edit; send a new message instead."""
        return await self.send_message(channel_id, content)

    async def delete_message(self, channel_id: str, message_id: str) -> bool:
        """Signal message deletion is not supported via the bridge."""
        return False

    async def add_reaction(self, channel_id: str, message_id: str, emoji: str) -> bool:
        """Reactions are not wired for Signal yet."""
        return False

    async def remove_reaction(self, channel_id: str, message_id: str, emoji: str) -> bool:
        """Reactions are not wired for Signal yet."""
        return False

    async def get_user(self, user_id: str) -> Optional[BotUser]:
        return BotUser(user_id=user_id, username=user_id)

    async def get_channel(self, channel_id: str) -> Optional[BotChannel]:
        return BotChannel(channel_id=channel_id, channel_type="dm")

    # ── Health & diagnostics ────────────────────────────────────────

    async def probe(self):
        """Test signal-cli-rest-api bridge reachability and account linkage."""
        from praisonaiagents.bots import ProbeResult

        started = time.time()
        try:
            import aiohttp

            session = self._http_session or aiohttp.ClientSession()
            close_after = self._http_session is None
            try:
                url = f"{self._bridge_url}/v1/accounts"
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    elapsed = (time.time() - started) * 1000
                    if resp.status == 200:
                        return ProbeResult(
                            ok=True, platform="signal", elapsed_ms=elapsed,
                            bot_username=self._account,
                            details={"bridge_url": self._bridge_url},
                        )
                    text = await resp.text()
                    return ProbeResult(
                        ok=False, platform="signal", elapsed_ms=elapsed,
                        error=f"HTTP {resp.status}: {text[:200]}",
                    )
            finally:
                if close_after:
                    await session.close()
        except Exception as e:  # noqa: BLE001
            return ProbeResult(
                ok=False, platform="signal",
                elapsed_ms=(time.time() - started) * 1000, error=str(e),
            )

    async def health(self):
        """Detailed health status (shared implementation)."""
        return await self._default_health()
