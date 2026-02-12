"""
WhatsApp Bot implementation for PraisonAI.

Provides a full WhatsApp bot runtime using the WhatsApp Cloud API (Meta Graph API).
Receives messages via an aiohttp webhook server and replies via REST API.

Requirements:
    - aiohttp (already a core dependency)
    - WHATSAPP_ACCESS_TOKEN: Meta Cloud API access token
    - WHATSAPP_PHONE_NUMBER_ID: Phone number ID from Meta
    - WHATSAPP_VERIFY_TOKEN: Custom string for webhook verification
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

from praisonai.bots._protocol_mixin import ChatCommandMixin
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


class WhatsAppBot(ChatCommandMixin):
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
        token: str,
        phone_number_id: str = "",
        agent: Optional["Agent"] = None,
        config: Optional[BotConfig] = None,
        verify_token: str = "",
        app_secret: str = "",
        webhook_port: int = 8080,
        webhook_path: str = "/webhook",
    ):
        self._token = token
        self._phone_number_id = phone_number_id or os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
        self._agent = agent
        self.config = config or BotConfig(token=token)
        self._verify_token = verify_token or os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
        self._app_secret = app_secret or os.environ.get("WHATSAPP_APP_SECRET", "")
        self._webhook_port = webhook_port
        self._webhook_path = webhook_path

        self._is_running = False
        self._started_at: Optional[float] = None
        self._bot_user: Optional[BotUser] = None
        self._session_mgr = BotSessionManager()
        self._message_handlers: List[Callable] = []
        self._runner: Any = None
        self._site: Any = None

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
        """Start the webhook server to receive WhatsApp messages."""
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

    async def stop(self) -> None:
        """Stop the webhook server."""
        self._is_running = False
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
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
                    await self.send_message(sender_id, str(response))
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
