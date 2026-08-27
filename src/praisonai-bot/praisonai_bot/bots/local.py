"""
Local (terminal) Bot implementation for PraisonAI.

A first-class ``local`` channel that reads stdin and writes stdout, so an
operator can converse with a gateway agent from their own shell — no provider
token, no webhook, no allowlist. It joins the *same* ``BotSessionManager``,
identity resolver, delivery router and cross-channel mirror as every remote
channel, so a conversation begun in the terminal continues seamlessly on a
remote platform (Telegram, Discord, …) under one resolved session id.

The adapter is owner-trusted by default: the local operator bypasses pairing
and allowlists, matching the "it's your own machine" trust model of a shell.

Usage::

    from praisonai_bot.bots import BotOS
    from praisonaiagents import Agent

    agent = Agent(name="assistant", instructions="Be helpful")
    BotOS(agent=agent, platforms=["local"]).run()   # chat in your terminal

Or alongside remote channels in one process::

    # gateway.yaml
    channels:
      local: {}
      telegram: { token: "..." }
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import sys
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

logger = logging.getLogger(__name__)

#: Stable identity for the local operator. Kept constant so the terminal maps to
#: one durable session across restarts (and, via the identity resolver, unifies
#: with a paired remote channel).
_LOCAL_USER_ID = "local-operator"
_LOCAL_CHAT_ID = "local"


class LocalDescriptor:
    """Self-description for the ``local`` channel (config keys + prompt hint).

    Declared so the gateway config schema, onboarding wizard and agent prompt
    wire the terminal as a first-class channel with zero core edits (see
    :class:`praisonaiagents.bots.protocols.ChannelDescriptor`). The channel is
    token-free, so it declares no required config fields.
    """

    config_fields: List[ChannelField] = [
        ChannelField(
            name="prompt",
            required=False,
            prompt="Terminal input prompt (default 'you> ')",
        ),
    ]
    system_prompt_hint = (
        "You are replying in a local terminal: keep replies plain text; there "
        "is no markdown rendering, no message editing and no rate limit."
    )


class LocalBot(ChatCommandMixin, MessageHookMixin):
    """Terminal (stdin/stdout) channel for PraisonAI agents.

    Owner-trusted, token-free. Shares the gateway's session manager, identity
    resolver and delivery router with every remote channel, so ``deliver="local"``
    resolves and cross-channel continuity works out of the box.

    Example::

        from praisonai_bot.bots import LocalBot
        from praisonaiagents import Agent

        agent = Agent(name="assistant")
        bot = LocalBot(agent=agent)
        await bot.start()
    """

    channel_descriptor = LocalDescriptor()

    def __init__(
        self,
        token: str = "",
        agent: Optional["Agent"] = None,
        config: Optional[BotConfig] = None,
        prompt: str = "you> ",
        **kwargs: Any,
    ):
        # ``token`` is accepted for parity with the generic Bot adapter wiring
        # (which always passes it); the local channel is token-free, so unused.
        self._extra_kwargs = kwargs
        self._agent = agent
        self.config = config or BotConfig(token="", mode="polling")
        self._prompt = prompt or "you> "

        self._is_running = False
        self._started_at: Optional[float] = None
        self._bot_user: Optional[BotUser] = None
        # Dedicated single daemon-thread executor for the blocking stdin read.
        # Using our own executor (rather than the loop's default) keeps the
        # blocking ``readline()`` off the default pool, so a shutdown that
        # cancels ``start()`` while a read is in flight never blocks
        # ``asyncio.run``'s ``shutdown_default_executor`` on a line/EOF that may
        # never arrive — the daemon thread is simply abandoned on interpreter
        # exit. Created lazily in ``start()``.
        self._read_executor: Optional[concurrent.futures.ThreadPoolExecutor] = None

        from ._session import build_session_manager
        # Exposed as ``_session`` (not ``_session_mgr``) so the gateway routing
        # handler and ``Bot._attach_gateway_runtime`` can splice the shared
        # identity resolver / delivery router / admission gate / turn-lock map
        # onto it — the same seam every built-in adapter exposes.
        self._session = build_session_manager(self.config, platform="local")
        self._message_handlers: List[Callable] = []

        self._command_handlers: Dict[str, Callable] = {}
        self._command_info: Dict[str, Dict[str, Any]] = {}
        self._register_builtins()

    # ── Capabilities ────────────────────────────────────────────────

    @classmethod
    def default_capabilities(cls) -> PlatformCapabilities:
        """Honest capability declaration so shared engines degrade correctly.

        A TTY has no markdown dialect, no rate limit and no webhook. Message
        editing is declared unsupported so streaming falls back to plain
        appends rather than assuming in-place terminal control.
        """
        return PlatformCapabilities(
            supports_edit=False,
            supports_typing=False,
            needs_rate_limit=False,
            accepts_webhooks=False,
            supports_media=False,
        )

    def _register_builtins(self) -> None:
        """Register built-in /status, /new, /help, /stop commands."""

        async def _status(msg):
            return format_status(self._agent, "local", self._started_at, self._is_running)

        async def _new(msg):
            self._session.reset(_LOCAL_USER_ID)
            return "Session reset. Send a message to start a new conversation."

        async def _help(msg):
            extra = {
                name: info.get("description", "")
                for name, info in self._command_info.items()
                if name not in ("status", "new", "help", "stop")
            }
            return format_help(self._agent, "local", extra or None)

        async def _stop(msg):
            return handle_stop_command(self._session, _LOCAL_USER_ID)

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
        return "local"

    @property
    def bot_user(self) -> Optional[BotUser]:
        return self._bot_user

    @property
    def supervised_inbound(self) -> bool:
        """A terminal has no reconnectable transport — never supervise it.

        Unlike a network channel, a closed stdin (EOF / Ctrl-D) is a clean
        end-of-session, not a dropped connection to reconnect. Opting out keeps
        ``Bot``/``BotOS`` from restarting the read loop after the user exits.
        """
        return False

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
        """Read a line at a time from stdin and route it to the agent."""
        self._is_running = True
        self._started_at = time.time()
        self._bot_user = BotUser(
            user_id=_LOCAL_USER_ID,
            username="local",
            display_name="Local",
            is_bot=True,
        )
        logger.info("Local channel reading from stdin (Ctrl-D to exit; /stop cancels the current run)")

        loop = asyncio.get_event_loop()
        self._read_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="praison-local-stdin",
        )
        try:
            while self._is_running:
                try:
                    # Read stdin off the event loop (on a dedicated daemon
                    # thread) so concurrent channels keep running while we wait
                    # for a line — and so a cancelled ``start()`` never blocks
                    # event-loop teardown on a read that may never complete.
                    line = await loop.run_in_executor(
                        self._read_executor, self._read_line
                    )
                except asyncio.CancelledError:
                    raise
                if line is None:  # EOF (Ctrl-D) — clean end of the terminal session
                    break
                text = line.strip()
                if not text:
                    continue
                try:
                    await self._handle_line(text)
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001 — one bad line must not kill the loop
                    logger.warning("Local channel error: %s", e)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    def _read_line(self) -> Optional[str]:
        """Blocking stdin read (run in an executor). Returns None on EOF."""
        try:
            sys.stdout.write(self._prompt)
            sys.stdout.flush()
        except Exception:  # noqa: BLE001 — prompt is cosmetic
            pass
        line = sys.stdin.readline()
        if line == "":
            return None
        return line

    async def stop(self) -> None:
        """Stop the read loop.

        Tears down the stdin read executor without waiting on the worker: a
        blocking ``sys.stdin.readline()`` cannot be interrupted from another
        thread, so joining it would re-introduce the shutdown hang this channel
        is designed to avoid. We abandon the (daemon-style) worker instead —
        an unread line is discarded, which is the correct behaviour for a
        terminal that is being torn down.
        """
        self._is_running = False
        executor = self._read_executor
        self._read_executor = None
        if executor is not None:
            try:
                # ``cancel_futures`` is available on 3.9+; drop still-queued
                # reads. ``wait=False`` guarantees we never block teardown on an
                # in-flight ``readline()`` that may never return.
                executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:  # pragma: no cover — very old Python
                executor.shutdown(wait=False)
        logger.info("Local channel stopped")

    # ── Receiving ───────────────────────────────────────────────────

    async def _handle_line(self, content: str) -> None:
        """Route one line of terminal input to the agent (or a command)."""
        sender = BotUser(
            user_id=_LOCAL_USER_ID,
            username="local",
            display_name="Local",
            is_bot=False,
        )
        channel = BotChannel(
            channel_id=_LOCAL_CHAT_ID,
            name="local",
            channel_type="dm",
        )
        bot_message = BotMessage(
            message_id=str(time.time()),
            content=content,
            message_type=MessageType.TEXT,
            sender=sender,
            channel=channel,
            timestamp=time.time(),
        )

        decision = self.fire_message_received(bot_message)
        if decision.get("drop"):
            logger.debug("Local message dropped by MESSAGE_RECEIVED hook")
            return
        content = decision.get("content", content)

        for handler in self._message_handlers:
            try:
                await handler(bot_message)
            except Exception as e:  # noqa: BLE001
                logger.error("Local message handler error: %s", e)

        text = content.strip()
        if text.startswith("/"):
            cmd_name = text.split()[0][1:].lower()
            cmd_handler = self._command_handlers.get(cmd_name)
            if cmd_handler:
                try:
                    response = await cmd_handler(bot_message)
                    if response:
                        await self.send_message(_LOCAL_CHAT_ID, response)
                except Exception as e:  # noqa: BLE001
                    logger.error("Local command '%s' error: %s", cmd_name, e)
                    await self.send_message(_LOCAL_CHAT_ID, f"Error: {e}")
                return

        if self._agent and content:
            try:
                response = await self._session.chat(
                    self._agent, _LOCAL_USER_ID, content,
                    chat_id=_LOCAL_CHAT_ID,
                    user_name="local",
                    message_id=bot_message.message_id,
                    account=getattr(self.config, "account", "default"),
                )
                if response:
                    send_result = self.fire_message_sending(_LOCAL_CHAT_ID, str(response))
                    if not send_result["cancel"]:
                        await self.send_message(_LOCAL_CHAT_ID, send_result["content"])
                        self.fire_message_sent(_LOCAL_CHAT_ID, send_result["content"])
            except Exception as e:  # noqa: BLE001
                logger.error("Local agent chat error: %s", e)
                await self.send_message(_LOCAL_CHAT_ID, failure_reply_text(e))

    # ── Sending ─────────────────────────────────────────────────────

    async def send_message(
        self,
        to: str,
        content: Union[str, Dict[str, Any]],
        reply_to: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> BotMessage:
        """Write a message to stdout.

        Accepts the same signature as remote adapters (including ``thread_id``)
        so the :class:`DeliveryRouter` can target ``deliver="local"`` uniformly;
        threads/replies have no meaning in a TTY and are ignored.
        """
        text = content if isinstance(content, str) else str(content)
        try:
            sys.stdout.write(text + "\n")
            sys.stdout.flush()
        except Exception as e:  # noqa: BLE001
            # Propagate: a failed terminal write means the message was NOT
            # delivered. Swallowing it here would make the shared DeliveryRouter
            # record a phantom success (skipping its failure handling/retries),
            # so we surface it like every other adapter's "raise on failure"
            # contract. ``_handle_line`` still guards its own sends, so a broken
            # stdout cannot kill the read loop.
            logger.debug("Local send failed: %s", e)
            raise
        return BotMessage(
            message_id=str(time.time()),
            content=text,
            message_type=MessageType.TEXT,
            sender=self._bot_user,
            channel=BotChannel(channel_id=to, channel_type="dm"),
        )

    async def get_user(self, user_id: str) -> Optional[BotUser]:
        return BotUser(user_id=user_id, username="local")

    async def get_channel(self, channel_id: str) -> Optional[BotChannel]:
        return BotChannel(channel_id=channel_id, channel_type="dm")

    # ── Health & diagnostics ────────────────────────────────────────

    async def probe(self):
        """The terminal is always reachable — a trivial always-ok probe."""
        from praisonaiagents.bots import ProbeResult

        return ProbeResult(
            ok=True,
            platform="local",
            elapsed_ms=0.0,
            bot_username="local",
            details={"tty": bool(getattr(sys.stdin, "isatty", lambda: False)())},
        )

    async def health(self):
        """Detailed health status (shared implementation)."""
        return await self._default_health()
