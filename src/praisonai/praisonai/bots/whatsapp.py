"""
WhatsApp Bot implementation for PraisonAI.

Supports two connection modes:

**Cloud API mode** (default, stable, recommended):
    - Uses Meta Graph API with webhook server
    - Requires: WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_VERIFY_TOKEN

**Web mode** (experimental, token-free):
    - Uses neonize (whatsmeow) for WhatsApp Web protocol
    - QR code scan via Linked Devices — no Meta developer account needed
    - ⚠️ Uses reverse-engineered protocol; your number may be banned

Usage:
    # Cloud API (default)
    bot = WhatsAppBot(token="EAAx...", phone_number_id="123", agent=agent)

    # Web mode (no tokens needed)
    bot = WhatsAppBot(mode="web", agent=agent)
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from praisonaiagents import Agent

from praisonai.bots._protocol_mixin import ChatCommandMixin, MessageHookMixin
from praisonaiagents.bots import (
    BotConfig,
    BotMessage,
    BotUser,
    BotChannel,
    MessageType,
)

from ._commands import format_status, format_help
from ._session import BotSessionManager

logger = logging.getLogger(__name__)

# Meta Graph API version
GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


class WhatsAppBot(ChatCommandMixin, MessageHookMixin):
    """WhatsApp bot runtime for PraisonAI agents.

    Connects an agent to WhatsApp via the Cloud API, handling messages,
    commands, and providing full bot functionality through a webhook server.

    Example:
        from praisonai.bots import WhatsAppBot
        from praisonaiagents import Agent

        agent = Agent(name="assistant")
        bot = WhatsAppBot(
            token="YOUR_ACCESS_TOKEN",
            phone_number_id="YOUR_PHONE_NUMBER_ID",
            agent=agent,
            verify_token="my-secret-verify-token",
        )

        await bot.start()
    """

    def __init__(
        self,
        token: str = "",
        phone_number_id: str = "",
        agent: Optional["Agent"] = None,
        config: Optional[BotConfig] = None,
        verify_token: str = "",
        app_secret: str = "",
        webhook_port: int = 8080,
        webhook_path: str = "/webhook",
        mode: str = "cloud",
        creds_dir: Optional[str] = None,
        allowed_numbers: Optional[List[str]] = None,
        allowed_groups: Optional[List[str]] = None,
        respond_to_all: bool = False,
    ):
        # Mode: "cloud" (default, Meta Cloud API) or "web" (neonize, experimental)
        self._mode = mode.lower().strip()
        if self._mode not in ("cloud", "web"):
            raise ValueError(f"Invalid mode '{self._mode}'. Use 'cloud' or 'web'.")

        self._token = token or os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
        self._phone_number_id = phone_number_id or os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
        self._agent = agent
        self.config = config or BotConfig(token=self._token)
        self._verify_token = verify_token or os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
        self._app_secret = app_secret or os.environ.get("WHATSAPP_APP_SECRET", "")
        self._webhook_port = webhook_port
        self._webhook_path = webhook_path
        self._creds_dir = creds_dir

        # Message filtering (Web mode).
        # Default: respond only to self-messages (IsFromMe).
        # --respond-to-all opens to everyone.
        # --respond-to / --respond-to-groups whitelist specific senders.
        self._respond_to_all = respond_to_all
        self._allowed_numbers: set[str] = set()
        self._allowed_groups: set[str] = set()
        if allowed_numbers:
            for n in allowed_numbers:
                # Normalise: strip +, keep digits only
                digits = "".join(c for c in n if c.isdigit())
                if digits:
                    self._allowed_numbers.add(digits)
        if allowed_groups:
            for g in allowed_groups:
                self._allowed_groups.add(g.strip())

        self._is_running = False
        self._started_at: Optional[float] = None
        self._bot_user: Optional[BotUser] = None
        self._session_mgr = BotSessionManager()
        self._message_handlers: List[Callable] = []
        self._runner: Any = None
        self._site: Any = None

        # Web mode adapter (lazy initialized)
        self._web_adapter: Any = None

        # ChatCommandMixin setup
        self._command_handlers: Dict[str, Callable] = {}
        self._command_info: Dict[str, Dict[str, Any]] = {}

        # Register built-in commands
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Register built-in /status, /new, /help commands."""

        async def _status(msg):
            return format_status(self._agent, "whatsapp", self._started_at, self._is_running)

        async def _new(msg):
            user_id = msg.sender.user_id if msg.sender else "unknown"
            self._session_mgr.reset(user_id)
            return "Session reset. Send a message to start a new conversation."

        async def _help(msg):
            extra = {
                name: info.get("description", "")
                for name, info in self._command_info.items()
                if name not in ("status", "new", "help")
            }
            return format_help(self._agent, "whatsapp", extra or None)

        self.register_command("status", _status, description="Show bot status and info")
        self.register_command("new", _new, description="Reset conversation session")
        self.register_command("help", _help, description="Show this help message")

    # ── Properties ──────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def platform(self) -> str:
        return "whatsapp"

    @property
    def mode(self) -> str:
        """Connection mode: 'cloud' (Meta Cloud API) or 'web' (neonize)."""
        return self._mode

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
        """Register a message handler."""
        self._message_handlers.append(handler)
        return handler

    def on_command(self, command: str) -> Callable:
        """Decorator to register a command handler."""
        def decorator(func: Callable) -> Callable:
            self.register_command(command, func)
            return func
        return decorator

    # ── Lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the bot in the configured mode (cloud or web)."""
        if self._mode == "web":
            await self._start_web_mode()
        else:
            await self._start_cloud_mode()

    async def _start_cloud_mode(self) -> None:
        """Start the Cloud API webhook server."""
        try:
            from aiohttp import web
        except ImportError:
            raise ImportError("aiohttp is required for WhatsApp bot. Install with: pip install aiohttp")

        app = web.Application()
        app.router.add_get(self._webhook_path, self._handle_verification)
        app.router.add_post(self._webhook_path, self._handle_webhook)
        app.router.add_get("/health", self._handle_health)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", self._webhook_port)

        self._is_running = True
        self._started_at = time.time()
        self._bot_user = BotUser(
            user_id=self._phone_number_id,
            username="whatsapp_bot",
            display_name="WhatsApp Bot",
            is_bot=True,
        )

        logger.info(f"WhatsApp webhook server starting on port {self._webhook_port}")
        logger.info(f"Webhook URL: http://0.0.0.0:{self._webhook_port}{self._webhook_path}")

        await self._site.start()

        # Keep running until cancelled
        try:
            while self._is_running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    async def _start_web_mode(self) -> None:
        """Start in Web mode using neonize (WhatsApp Web protocol).

        ⚠️ EXPERIMENTAL: Uses reverse-engineered protocol.
        """
        from ._whatsapp_web_adapter import WhatsAppWebAdapter

        async def _on_web_message(event: Any) -> None:
            """Bridge neonize message events to bot message handling."""
            try:
                # Extract message info from neonize event
                info = getattr(event, 'Info', None) or getattr(event, 'info', None)
                msg = getattr(event, 'Message', None) or getattr(event, 'message', None)
                if not info or not msg:
                    return

                # Extract message source fields
                msg_source = getattr(info, 'MessageSource', None) or info
                sender_jid = str(getattr(msg_source, 'Sender', '') or getattr(info, 'sender', ''))
                # Keep the original neonize JID protobuf for Chat — this
                # preserves LID routing info needed by send_message.
                chat_jid_obj = getattr(msg_source, 'Chat', None) or getattr(info, 'chat', None)
                chat_jid = str(chat_jid_obj) if chat_jid_obj else ''
                msg_id = str(getattr(info, 'ID', '') or getattr(info, 'id', ''))
                raw_ts = getattr(info, 'Timestamp', None)
                if hasattr(raw_ts, 'timestamp'):
                    timestamp = raw_ts.timestamp()
                elif isinstance(raw_ts, (int, float)) and raw_ts > 0:
                    # neonize/Go encodes timestamps as milliseconds (UnixMilli).
                    # Detect: any value > 1e12 is milliseconds, convert to seconds.
                    timestamp = raw_ts / 1000.0 if raw_ts > 1e12 else float(raw_ts)
                else:
                    timestamp = time.time()

                # ── Stale-message guard ────────────────────────────────
                # whatsmeow delivers offline/historical messages as regular
                # MessageEv upon reconnection.  Drop anything older than
                # the moment the adapter actually connected so the bot
                # never replies to old messages.
                connected_at = (
                    self._web_adapter.connected_at
                    if self._web_adapter else self._started_at
                ) or self._started_at or 0
                if timestamp and connected_at and timestamp < connected_at:
                    logger.debug(
                        "Skipping stale message %s (ts=%.1f < connected=%.1f)",
                        msg_id, timestamp, connected_at,
                    )
                    return

                # ── Message filtering ────────────────────────────────
                # Default: self-chat only (user messaging their own number).
                # Expand via allowed_numbers / groups / respond_to_all.
                is_from_me = bool(getattr(msg_source, 'IsFromMe', False))
                is_group = bool(getattr(msg_source, 'IsGroup', False)) or "@g.us" in chat_jid

                # Determine if this is a true self-chat (user→own number).
                # IsFromMe is True for ANY message the user sent in any chat,
                # but self-messaging means sender and chat are the same JID.
                def _jid_user(jid_str: str) -> str:
                    """Extract bare user part from a JID string."""
                    return jid_str.split("@")[0].split(":")[0] if jid_str else ""

                is_self_chat = (
                    is_from_me
                    and not is_group
                    and _jid_user(sender_jid) == _jid_user(chat_jid)
                )

                if not self._respond_to_all:
                    if is_self_chat:
                        pass  # true self-chat — always allow
                    elif is_group and self._allowed_groups:
                        # Check if group JID is in the allowlist
                        chat_jid_str = chat_jid.split("@")[0] if "@" in chat_jid else chat_jid
                        if not (chat_jid in self._allowed_groups
                                or chat_jid_str in self._allowed_groups):
                            logger.debug("Filtered: group %s not in allowlist", chat_jid)
                            return
                    elif not is_group and self._allowed_numbers:
                        # Check if sender number is in the allowlist
                        sender_num = _jid_user(sender_jid)
                        if sender_num not in self._allowed_numbers:
                            logger.debug("Filtered: sender %s not in allowlist", sender_num)
                            return
                    else:
                        # Not self-chat, not in any allowlist → ignore
                        logger.debug(
                            "Filtered: msg %s (from_me=%s, self_chat=%s, group=%s)",
                            msg_id, is_from_me, is_self_chat, is_group,
                        )
                        return

                # Extract text content
                content = ""
                conversation = getattr(msg, 'conversation', None)
                ext_text = getattr(msg, 'extendedTextMessage', None)
                if conversation:
                    content = str(conversation)
                elif ext_text:
                    content = str(getattr(ext_text, 'text', ''))
                else:
                    content = "[Non-text message received]"

                if not content:
                    return

                # Determine if group
                is_group = "@g.us" in chat_jid
                sender_name = sender_jid.split("@")[0] if sender_jid else "unknown"

                sender = BotUser(
                    user_id=sender_jid,
                    username=sender_name,
                    display_name=sender_name,
                    is_bot=False,
                )
                channel = BotChannel(
                    channel_id=chat_jid,
                    name=f"whatsapp:{chat_jid}",
                    channel_type="group" if is_group else "dm",
                )

                bot_message = BotMessage(
                    message_id=msg_id,
                    content=content,
                    message_type=MessageType.TEXT,
                    sender=sender,
                    channel=channel,
                    timestamp=float(timestamp) if timestamp else time.time(),
                )

                self.fire_message_received(bot_message)

                # Fire registered message handlers
                for handler in self._message_handlers:
                    try:
                        await handler(bot_message)
                    except Exception as e:
                        logger.error(f"Message handler error: {e}")

                # Check for commands
                text = content.strip()
                if text.startswith("/"):
                    cmd_name = text.split()[0][1:].lower()
                    cmd_handler = self._command_handlers.get(cmd_name)
                    if cmd_handler:
                        try:
                            response = await cmd_handler(bot_message)
                            if response:
                                await self._web_send(chat_jid_obj or chat_jid, response)
                        except Exception as e:
                            logger.error(f"Command '{cmd_name}' error: {e}")
                            await self._web_send(chat_jid, f"Error: {e}")
                        return

                # Route to agent
                if self._agent and content:
                    try:
                        response = await self._session_mgr.chat(
                            self._agent, sender_jid, content
                        )
                        if response:
                            send_result = self.fire_message_sending(chat_jid, str(response))
                            if not send_result["cancel"]:
                                await self._web_send(chat_jid_obj or chat_jid, send_result["content"])
                                self.fire_message_sent(chat_jid, send_result["content"])
                    except Exception as e:
                        logger.error(f"Agent chat error: {e}")
                        await self._web_send(chat_jid, "Sorry, I encountered an error.")

            except Exception as e:
                logger.error(f"Web mode message processing error: {e}")

        async def _on_connected() -> None:
            logger.info("WhatsApp Web: connected and ready")

        self._web_adapter = WhatsAppWebAdapter(
            creds_dir=self._creds_dir,
            on_message=_on_web_message,
            on_connected=_on_connected,
        )

        self._is_running = True
        self._started_at = time.time()
        self._bot_user = BotUser(
            user_id="web_user",
            username="whatsapp_web_bot",
            display_name="WhatsApp Web Bot",
            is_bot=True,
        )

        has_session = self._web_adapter.has_saved_session()
        if has_session:
            logger.info("WhatsApp Web: using saved session")
        else:
            logger.info("WhatsApp Web: no saved session — QR code will be displayed")

        try:
            await self._web_adapter.connect()
            # Keep running
            while self._is_running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        except KeyboardInterrupt:
            pass
        except Exception as e:
            logger.error(f"WhatsApp Web mode error: {e}")
            raise
        finally:
            # Graceful shutdown: stop the neonize log worker thread to
            # prevent "threading._shutdown" errors on Ctrl+C.
            try:
                from neonize.utils.log import shutdown_log_worker
                shutdown_log_worker()
            except Exception:
                pass
            await self.stop()

    async def _web_send(self, to: Any, text: str) -> None:
        """Send message via Web mode adapter.

        Args:
            to: Recipient — a native neonize JID protobuf (preferred) or
                a JID string as fallback.
            text: Message text.
        """
        if self._web_adapter and self._web_adapter.is_connected:
            await self._web_adapter.send_message(to, text)

    async def stop(self) -> None:
        """Stop the bot (both Cloud and Web modes)."""
        self._is_running = False
        # Cloud mode cleanup
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        # Web mode cleanup
        if self._web_adapter:
            try:
                await self._web_adapter.disconnect()
            except Exception as e:
                logger.warning(f"Web adapter disconnect error: {e}")
        logger.info("WhatsApp bot stopped")

    # ── Webhook handlers ────────────────────────────────────────────

    async def _handle_verification(self, request) -> Any:
        """Handle webhook verification (GET request from Meta).

        Meta sends: ?hub.mode=subscribe&hub.verify_token=<token>&hub.challenge=<challenge>
        We must respond with the challenge if the verify_token matches.
        """
        from aiohttp import web

        mode = request.query.get("hub.mode", "")
        token = request.query.get("hub.verify_token", "")
        challenge = request.query.get("hub.challenge", "")

        if mode == "subscribe" and token == self._verify_token:
            logger.info("Webhook verification successful")
            return web.Response(text=challenge, content_type="text/plain")
        else:
            logger.warning(f"Webhook verification failed: mode={mode}")
            return web.Response(status=403, text="Verification failed")

    async def _handle_health(self, request) -> Any:
        """Health check endpoint."""
        from aiohttp import web

        return web.json_response({
            "status": "healthy",
            "platform": "whatsapp",
            "is_running": self._is_running,
            "uptime": int(time.time() - self._started_at) if self._started_at else 0,
        })

    async def _handle_webhook(self, request) -> Any:
        """Handle incoming webhook POST from WhatsApp Cloud API."""
        from aiohttp import web

        try:
            body = await request.read()

            # Verify signature if app_secret is configured
            if self._app_secret:
                signature = request.headers.get("X-Hub-Signature-256", "")
                if not self._verify_signature(body, signature):
                    logger.warning("Invalid webhook signature")
                    return web.Response(status=403, text="Invalid signature")

            data = json.loads(body)
        except Exception as e:
            logger.error(f"Failed to parse webhook body: {e}")
            return web.Response(status=400, text="Bad request")

        # Process asynchronously so we respond 200 immediately
        asyncio.create_task(self._process_webhook_data(data))

        # Always respond 200 to acknowledge receipt
        return web.Response(status=200, text="OK")

    def _verify_signature(self, body: bytes, signature: str) -> bool:
        """Verify webhook signature using app secret."""
        if not signature.startswith("sha256="):
            return False
        expected = hmac.new(
            self._app_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)

    async def _process_webhook_data(self, data: dict) -> None:
        """Process webhook data and route to appropriate handler."""
        try:
            entry = data.get("entry", [])
            for e in entry:
                changes = e.get("changes", [])
                for change in changes:
                    value = change.get("value", {})
                    messages = value.get("messages", [])
                    contacts = value.get("contacts", [])

                    for msg in messages:
                        contact = contacts[0] if contacts else {}
                        await self._handle_incoming_message(msg, contact, value)
        except Exception as e:
            logger.error(f"Error processing webhook data: {e}")

    async def _handle_incoming_message(
        self, msg: dict, contact: dict, value: dict
    ) -> None:
        """Handle a single incoming WhatsApp message."""
        msg_type = msg.get("type", "text")
        sender_id = msg.get("from", "")
        msg_id = msg.get("id", "")
        timestamp = msg.get("timestamp", "")

        # Build sender
        sender = BotUser(
            user_id=sender_id,
            username=sender_id,
            display_name=contact.get("profile", {}).get("name", sender_id),
            is_bot=False,
        )

        # Build channel (WhatsApp is always DM-like)
        channel = BotChannel(
            channel_id=sender_id,
            name=f"whatsapp:{sender_id}",
            channel_type="dm",
        )

        # Extract message content
        content = ""
        bot_message_type = MessageType.TEXT

        if msg_type == "text":
            content = msg.get("text", {}).get("body", "")
        elif msg_type == "image":
            content = msg.get("image", {}).get("caption", "[Image received]")
            bot_message_type = MessageType.IMAGE
        elif msg_type == "audio":
            content = "[Audio received]"
            bot_message_type = MessageType.AUDIO
        elif msg_type == "video":
            content = msg.get("video", {}).get("caption", "[Video received]")
            bot_message_type = MessageType.VIDEO
        elif msg_type == "document":
            content = msg.get("document", {}).get("caption", "[Document received]")
            bot_message_type = MessageType.FILE
        elif msg_type == "location":
            loc = msg.get("location", {})
            content = f"Location: {loc.get('latitude', 0)}, {loc.get('longitude', 0)}"
            bot_message_type = MessageType.LOCATION
        elif msg_type == "reaction":
            content = msg.get("reaction", {}).get("emoji", "")
            bot_message_type = MessageType.REACTION
        else:
            content = f"[{msg_type} message received]"

        bot_message = BotMessage(
            message_id=msg_id,
            content=content,
            message_type=bot_message_type,
            sender=sender,
            channel=channel,
            timestamp=float(timestamp) if timestamp else time.time(),
        )

        self.fire_message_received(bot_message)

        # Fire registered message handlers (e.g., gateway routing)
        for handler in self._message_handlers:
            try:
                await handler(bot_message)
            except Exception as e:
                logger.error(f"Message handler error: {e}")

        # Check for commands
        text = content.strip()
        if text.startswith("/"):
            cmd_name = text.split()[0][1:].lower()
            handler = self._command_handlers.get(cmd_name)
            if handler:
                try:
                    response = await handler(bot_message)
                    if response:
                        await self.send_message(sender_id, response)
                except Exception as e:
                    logger.error(f"Command '{cmd_name}' error: {e}")
                    await self.send_message(sender_id, f"Error: {e}")
                return

        # Route to agent
        if self._agent and content:
            try:
                response = await self._session_mgr.chat(
                    self._agent, sender_id, content
                )
                if response:
                    send_result = self.fire_message_sending(sender_id, str(response))
                    if not send_result["cancel"]:
                        await self.send_message(sender_id, send_result["content"])
                        self.fire_message_sent(sender_id, send_result["content"])
            except Exception as e:
                logger.error(f"Agent chat error: {e}")
                await self.send_message(sender_id, "Sorry, I encountered an error processing your message.")

    # ── Sending messages ────────────────────────────────────────────

    async def send_message(
        self,
        to: str,
        content: Union[str, Dict[str, Any]],
        reply_to: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> BotMessage:
        """Send a text message via WhatsApp Cloud API."""
        try:
            import aiohttp
        except ImportError:
            raise ImportError("aiohttp is required for WhatsApp bot")

        text = content if isinstance(content, str) else json.dumps(content)

        # Split long messages (WhatsApp limit: 4096 chars)
        max_len = self.config.max_message_length
        chunks = [text[i:i + max_len] for i in range(0, len(text), max_len)]

        sent_msg = None
        for chunk in chunks:
            url = f"{GRAPH_API_BASE}/{self._phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            }
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": chunk},
            }

            # Add reply context if provided
            if reply_to:
                payload["context"] = {"message_id": reply_to}

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        result = await resp.json()
                        if "error" in result:
                            logger.error(f"WhatsApp send error: {result['error']}")
                        else:
                            msg_id = result.get("messages", [{}])[0].get("id", "")
                            sent_msg = BotMessage(
                                message_id=msg_id,
                                content=chunk,
                                message_type=MessageType.TEXT,
                                sender=self._bot_user,
                                channel=BotChannel(channel_id=to, channel_type="dm"),
                            )
            except Exception as e:
                logger.error(f"Failed to send WhatsApp message: {e}")

        return sent_msg or BotMessage(content=text)

    async def send_template(
        self,
        to: str,
        template_name: str,
        language: str = "en_US",
        components: Optional[List[Dict[str, Any]]] = None,
    ) -> BotMessage:
        """Send a template message via WhatsApp Cloud API."""
        try:
            import aiohttp
        except ImportError:
            raise ImportError("aiohttp is required for WhatsApp bot")

        url = f"{GRAPH_API_BASE}/{self._phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
            },
        }
        if components:
            payload["template"]["components"] = components

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    result = await resp.json()
                    if "error" in result:
                        logger.error(f"WhatsApp template error: {result['error']}")
                    msg_id = result.get("messages", [{}])[0].get("id", "")
                    return BotMessage(
                        message_id=msg_id,
                        content=f"[Template: {template_name}]",
                        sender=self._bot_user,
                        channel=BotChannel(channel_id=to, channel_type="dm"),
                    )
        except Exception as e:
            logger.error(f"Failed to send template: {e}")
            return BotMessage(content=f"[Template: {template_name}]")

    async def send_reaction(self, to: str, message_id: str, emoji: str) -> None:
        """Send a reaction to a message."""
        try:
            import aiohttp
        except ImportError:
            return

        url = f"{GRAPH_API_BASE}/{self._phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "reaction",
            "reaction": {"message_id": message_id, "emoji": emoji},
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    await resp.json()
        except Exception as e:
            logger.error(f"Failed to send reaction: {e}")

    async def mark_as_read(self, message_id: str) -> None:
        """Mark a message as read."""
        try:
            import aiohttp
        except ImportError:
            return

        url = f"{GRAPH_API_BASE}/{self._phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    await resp.json()
        except Exception as e:
            logger.error(f"Failed to mark as read: {e}")

    # ── Convenience ─────────────────────────────────────────────────

    async def edit_message(self, channel_id: str, message_id: str, content: Union[str, Dict[str, Any]]) -> BotMessage:
        """WhatsApp doesn't support editing messages. Send a new one instead."""
        return await self.send_message(channel_id, content)

    async def delete_message(self, channel_id: str, message_id: str) -> bool:
        """WhatsApp doesn't support deleting sent messages."""
        return False

    async def send_typing(self, channel_id: str) -> None:
        """WhatsApp doesn't have a typing indicator API."""
        pass

    async def get_user(self, user_id: str) -> Optional[BotUser]:
        """Get user info (limited in WhatsApp API)."""
        return BotUser(user_id=user_id, username=user_id)

    async def get_channel(self, channel_id: str) -> Optional[BotChannel]:
        """Get channel info (WhatsApp is DM-only)."""
        return BotChannel(channel_id=channel_id, channel_type="dm")

    async def probe(self):
        """Test WhatsApp Cloud API connectivity."""
        from praisonaiagents.bots import ProbeResult
        started = time.time()
        if self._mode == "web":
            return ProbeResult(ok=True, platform="whatsapp", elapsed_ms=0.0, details={"mode": "web"})
        try:
            import aiohttp
            url = f"{GRAPH_API_BASE}/{self._phone_number_id}"
            headers = {"Authorization": f"Bearer {self._token}"}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    elapsed = (time.time() - started) * 1000
                    if resp.status == 200:
                        data = await resp.json()
                        return ProbeResult(
                            ok=True, platform="whatsapp", elapsed_ms=elapsed,
                            bot_username=data.get("display_phone_number", self._phone_number_id),
                            details={"phone_number_id": self._phone_number_id, "verified_name": data.get("verified_name")},
                        )
                    else:
                        text = await resp.text()
                        return ProbeResult(ok=False, platform="whatsapp", elapsed_ms=elapsed, error=f"HTTP {resp.status}: {text[:200]}")
        except Exception as e:
            return ProbeResult(ok=False, platform="whatsapp", elapsed_ms=(time.time() - started) * 1000, error=str(e))

    async def health(self):
        """Get detailed health status of the WhatsApp bot."""
        from praisonaiagents.bots import HealthResult
        probe_result = await self.probe()
        uptime = (time.time() - self._started_at) if self._started_at else None
        session_count = len(self._session._histories) if hasattr(self._session, '_histories') else 0
        return HealthResult(
            ok=self._is_running and probe_result.ok, platform="whatsapp",
            is_running=self._is_running, uptime_seconds=uptime,
            probe=probe_result, sessions=session_count,
            error=probe_result.error if not probe_result.ok else None,
        )
