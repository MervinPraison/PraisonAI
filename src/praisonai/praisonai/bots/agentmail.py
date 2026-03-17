"""
AgentMail Bot implementation for PraisonAI.

Provides an agent-native email bot using the AgentMail API for zero-config
email functionality. No IMAP/SMTP setup required.

Requires: pip install agentmail
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
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
    ProbeResult,
    HealthResult,
)

from ._session import BotSessionManager
from ._email_utils import is_auto_reply, is_blocked_sender, extract_email_address

logger = logging.getLogger(__name__)


class AgentMailBot(ChatCommandMixin, MessageHookMixin):
    """Agent-native email bot using AgentMail API.
    
    Zero-config email for agents — no IMAP/SMTP setup required.
    Creates dedicated inboxes programmatically via AgentMail API.
    
    Example:
        from praisonai.bots import AgentMailBot
        from praisonaiagents import Agent
        
        agent = Agent(name="email_assistant")
        bot = AgentMailBot(
            token="am_...",  # AGENTMAIL_API_KEY
            agent=agent,
        )
        
        await bot.start()
        print(bot.email_address)  # agent-123@agentmail.to
    
    Environment variables (if not passed directly):
        AGENTMAIL_API_KEY: API key for AgentMail service
        AGENTMAIL_INBOX_ID: Optional existing inbox ID to reuse
        AGENTMAIL_DOMAIN: Optional custom domain for inbox creation
    """
    
    def __init__(
        self,
        token: str,
        agent: Optional["Agent"] = None,
        config: Optional[BotConfig] = None,
        inbox_id: Optional[str] = None,
        domain: Optional[str] = None,
        polling_interval: int = 10,
        mode: Optional[str] = None,
        webhook_port: Optional[int] = None,
        **kwargs,
    ):
        """Initialize AgentMailBot.
        
        Args:
            token: AgentMail API key (or set AGENTMAIL_API_KEY env var)
            agent: PraisonAI agent to handle messages
            config: Bot configuration
            inbox_id: Existing inbox ID to reuse (optional)
            domain: Custom domain for new inbox (optional)
            polling_interval: Seconds between polling for new messages
            mode: Event mode — poll (default), ws, webhook, or hybrid
            webhook_port: Port for webhook server (default: 8080)
            **kwargs: Additional configuration
        """
        self._token = token or os.getenv("AGENTMAIL_API_KEY", "")
        self._agent = agent
        self._inbox_id = inbox_id or os.getenv("AGENTMAIL_INBOX_ID")
        self._domain = domain or os.getenv("AGENTMAIL_DOMAIN")
        self._polling_interval = polling_interval
        
        # Bot state
        self._is_running = False
        self._started_at: Optional[float] = None
        self._bot_user: Optional[BotUser] = None
        self._email_address: Optional[str] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        
        # AgentMail clients (lazy loaded)
        self._client: Any = None
        self._async_client: Any = None
        
        # Webhook server state
        self._webhook_runner: Any = None
        self._webhook_site: Any = None
        
        # Session manager for conversation state
        self.config = config or BotConfig()
        self._session = BotSessionManager(self.config)
        
        # Resolve mode: explicit param > config > default
        if mode:
            self._mode = mode
        elif self.config.mode != "poll":
            self._mode = self.config.mode
        else:
            self._mode = "poll"
        
        # Resolve webhook port
        self._webhook_port = webhook_port or self.config.webhook_port
        
        # Command and message handlers
        self._command_handlers: Dict[str, Callable] = {}
        self._message_handlers: List[Callable] = []
        
        # Track processed message IDs to avoid duplicates
        self._processed_ids: set = set()
    
    @property
    def platform(self) -> str:
        """Platform identifier."""
        return "agentmail"
    
    @property
    def is_running(self) -> bool:
        """Whether the bot is currently running."""
        return self._is_running
    
    @property
    def bot_user(self) -> Optional[BotUser]:
        """The bot's user identity."""
        return self._bot_user
    
    @property
    def email_address(self) -> Optional[str]:
        """The bot's email address."""
        return self._email_address
    
    def get_agent(self) -> Optional["Agent"]:
        """Get the associated agent."""
        return self._agent
    
    def set_agent(self, agent: "Agent") -> None:
        """Set the associated agent."""
        self._agent = agent
    
    def _get_client(self) -> Any:
        """Lazy load sync AgentMail client."""
        if self._client is None:
            try:
                from agentmail import AgentMail
                self._client = AgentMail(api_key=self._token)
            except ImportError:
                raise ImportError(
                    "AgentMail package not installed. "
                    "Install with: pip install agentmail"
                )
        return self._client
    
    def _get_async_client(self) -> Any:
        """Lazy load async AgentMail client (for WS mode)."""
        if self._async_client is None:
            try:
                from agentmail import AsyncAgentMail
                self._async_client = AsyncAgentMail(api_key=self._token)
            except ImportError:
                raise ImportError(
                    "AgentMail package not installed. "
                    "Install with: pip install agentmail"
                )
        return self._async_client
    
    async def start(self) -> None:
        """Start the AgentMail bot.
        
        Creates or connects to an inbox and begins receiving messages
        using the configured mode (poll, ws, webhook, or hybrid).
        """
        if self._is_running:
            logger.warning("AgentMailBot is already running")
            return
        
        if not self._token:
            raise ValueError(
                "AgentMail API key required. Set AGENTMAIL_API_KEY env var or pass token parameter."
            )
        
        client = self._get_client()
        
        # Create or get inbox
        if self._inbox_id:
            # Use existing inbox — inbox_id IS the email address in AgentMail SDK
            self._email_address = self._inbox_id
            logger.info(f"Using existing AgentMail inbox: {self._email_address}")
        else:
            # Create new inbox
            try:
                inbox_params = {}
                if self._domain:
                    inbox_params["domain"] = self._domain
                inbox = client.inboxes.create(**inbox_params)
                # SDK v0.4.7: inbox_id IS the email address (e.g. "user@agentmail.to")
                self._inbox_id = inbox.inbox_id
                self._email_address = inbox.inbox_id
                logger.info(f"Created AgentMail inbox: {self._email_address}")
            except Exception as e:
                raise ConnectionError(f"Failed to create inbox: {e}")
        
        self._bot_user = BotUser(
            user_id=self._inbox_id,
            username=self._email_address,
            display_name=self._email_address.split("@")[0] if self._email_address else "agent",
            is_bot=True,
        )
        
        self._is_running = True
        self._started_at = time.time()
        self._stop_event.clear()
        
        # Branch on mode
        if self._mode == "ws":
            self._ws_task = asyncio.create_task(self._ws_loop())
            logger.info(f"AgentMailBot started (ws): {self._email_address}")
        elif self._mode == "webhook":
            await self._start_webhook_mode()
            logger.info(f"AgentMailBot started (webhook): {self._email_address}")
        elif self._mode == "hybrid":
            self._ws_task = asyncio.create_task(self._ws_loop())
            self._poll_task = asyncio.create_task(
                self._poll_loop(interval_override=60)
            )
            logger.info(f"AgentMailBot started (hybrid): {self._email_address}")
        else:
            # Default: poll mode (existing behaviour — zero breaking change)
            self._poll_task = asyncio.create_task(self._poll_loop())
            logger.info(f"AgentMailBot started (poll): {self._email_address}")
    
    async def stop(self) -> None:
        """Stop the AgentMail bot."""
        if not self._is_running:
            return
        
        self._is_running = False
        self._stop_event.set()
        
        # Cancel poll task
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        
        # Cancel WS task
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            self._ws_task = None
        
        # Stop webhook server
        if self._webhook_site:
            await self._webhook_site.stop()
            self._webhook_site = None
        if self._webhook_runner:
            await self._webhook_runner.cleanup()
            self._webhook_runner = None
        
        logger.info("AgentMailBot stopped")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Poll mode (existing behaviour)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    async def _poll_loop(self, interval_override: Optional[int] = None) -> None:
        """Poll for new messages.
        
        Args:
            interval_override: Override polling interval (used by hybrid mode 
                              to set a slower 60s fallback poll).
        """
        interval = interval_override or self._polling_interval
        while self._is_running:
            try:
                await self._check_new_messages()
            except Exception as e:
                logger.error(f"Error checking messages: {e}")
            
            # Wait for interval or stop signal
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=interval
                )
                break  # Stop event was set
            except asyncio.TimeoutError:
                continue  # Normal timeout, continue polling
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # WebSocket mode
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    async def _ws_loop(self) -> None:
        """WebSocket event loop with auto-reconnect.
        
        Connects to AgentMail WebSocket API, subscribes to message.received
        events for this inbox, and processes them via _handle_message.
        Reconnects with exponential backoff on disconnection.
        """
        backoff = 1  # Start at 1s
        max_backoff = 60
        
        while self._is_running:
            try:
                await self._ws_connect_and_listen()
                # If we exit cleanly (stop called), break
                if not self._is_running:
                    break
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if not self._is_running:
                    break
                logger.warning(
                    f"WebSocket disconnected: {e}. "
                    f"Reconnecting in {backoff}s..."
                )
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=backoff
                    )
                    break  # Stop was requested during backoff
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * 2, max_backoff)
            else:
                # Reset backoff on clean disconnect
                backoff = 1
    
    async def _ws_connect_and_listen(self) -> None:
        """Single WebSocket connection session."""
        try:
            from agentmail import AsyncAgentMail, Subscribe, MessageReceivedEvent
        except ImportError:
            raise ImportError(
                "AgentMail package not installed. "
                "Install with: pip install agentmail"
            )
        
        async_client = self._get_async_client()
        
        async with async_client.websockets.connect() as ws:
            # Subscribe to message.received events for this inbox
            await ws.send_subscribe(
                Subscribe(
                    event_types=["message.received"],
                    inbox_ids=[self._inbox_id] if self._inbox_id else None,
                )
            )
            logger.info(f"WebSocket connected, subscribed to {self._inbox_id}")
            
            async for event in ws:
                if not self._is_running:
                    break
                
                if isinstance(event, MessageReceivedEvent):
                    await self._handle_ws_event(event)
    
    async def _handle_ws_event(self, event: Any) -> None:
        """Convert a WebSocket MessageReceivedEvent to BotMessage and handle."""
        try:
            msg_id = getattr(event, 'message_id', None)
            if not msg_id:
                return
            
            # Dedup — shared with poll mode
            if msg_id in self._processed_ids:
                return
            self._processed_ids.add(msg_id)
            
            sender_raw = getattr(event, 'from_', '') or ''
            sender_email = extract_email_address(sender_raw)
            
            # Skip auto-replies and blocked senders
            headers = getattr(event, 'headers', {}) or {}
            if is_auto_reply(headers):
                logger.debug(f"Skipping auto-reply from {sender_email}")
                return
            if is_blocked_sender(sender_email):
                logger.debug(f"Skipping blocked sender: {sender_email}")
                return
            
            body = getattr(event, 'extracted_text', '') or getattr(event, 'text', '') or ''
            
            message = BotMessage(
                message_id=msg_id,
                content=body,
                message_type=MessageType.TEXT,
                sender=BotUser(
                    user_id=sender_email,
                    username=sender_email,
                    display_name=sender_email.split("@")[0] if sender_email else "unknown",
                ),
                channel=BotChannel(
                    channel_id=self._inbox_id,
                    name=self._email_address or self._inbox_id,
                ),
                thread_id=getattr(event, 'thread_id', None),
                metadata={
                    "subject": getattr(event, 'subject', ''),
                    "message_id": msg_id,
                    "in_reply_to": getattr(event, 'in_reply_to', ''),
                    "source": "websocket",
                },
            )
            
            await self._handle_message(message)
            
        except Exception as e:
            logger.error(f"Error handling WS event: {e}")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Webhook mode
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    async def _start_webhook_mode(self) -> None:
        """Start an aiohttp webhook server to receive AgentMail events."""
        try:
            from aiohttp import web
        except ImportError:
            raise ImportError(
                "aiohttp required for webhook mode. "
                "Install with: pip install aiohttp"
            )
        
        app = web.Application()
        webhook_path = self.config.webhook_path or "/webhook"
        app.router.add_post(webhook_path, self._handle_email_webhook)
        app.router.add_get("/health", self._handle_health_check)
        
        self._webhook_runner = web.AppRunner(app)
        await self._webhook_runner.setup()
        self._webhook_site = web.TCPSite(
            self._webhook_runner, "0.0.0.0", self._webhook_port
        )
        await self._webhook_site.start()
        
        logger.info(
            f"Webhook server listening on 0.0.0.0:{self._webhook_port}{webhook_path}"
        )
        
        # Register webhook with AgentMail API
        if self.config.webhook_url:
            try:
                client = self._get_client()
                webhook_url = self.config.webhook_url.rstrip("/") + webhook_path
                client.webhooks.create(
                    url=webhook_url,
                    event_types=["message.received"],
                    inbox_ids=[self._inbox_id] if self._inbox_id else None,
                )
                logger.info(f"Registered webhook: {webhook_url}")
            except Exception as e:
                logger.warning(f"Failed to register webhook with AgentMail: {e}")
    
    async def _handle_email_webhook(self, request: Any) -> Any:
        """Handle incoming webhook POST from AgentMail."""
        from aiohttp import web
        
        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text="Invalid JSON")
        
        # Extract event type
        event_type = body.get("type", "")
        if event_type != "message.received":
            return web.Response(status=200, text="OK")
        
        # Process asynchronously — return 200 immediately
        asyncio.create_task(self._process_webhook_payload(body))
        return web.Response(status=200, text="OK")
    
    async def _process_webhook_payload(self, body: Dict[str, Any]) -> None:
        """Process a webhook payload in the background."""
        try:
            data = body.get("data", body)
            msg_id = data.get("message_id", "")
            
            if not msg_id:
                return
            
            # Dedup
            if msg_id in self._processed_ids:
                return
            self._processed_ids.add(msg_id)
            
            sender_raw = data.get("from", data.get("from_", ""))
            sender_email = extract_email_address(sender_raw)
            
            headers = data.get("headers", {})
            if is_auto_reply(headers):
                return
            if is_blocked_sender(sender_email):
                return
            
            body_text = data.get("extracted_text", "") or data.get("text", "")
            
            message = BotMessage(
                message_id=msg_id,
                content=body_text,
                message_type=MessageType.TEXT,
                sender=BotUser(
                    user_id=sender_email,
                    username=sender_email,
                    display_name=sender_email.split("@")[0] if sender_email else "unknown",
                ),
                channel=BotChannel(
                    channel_id=self._inbox_id,
                    name=self._email_address or self._inbox_id,
                ),
                thread_id=data.get("thread_id"),
                metadata={
                    "subject": data.get("subject", ""),
                    "message_id": msg_id,
                    "in_reply_to": data.get("in_reply_to", ""),
                    "source": "webhook",
                },
            )
            
            await self._handle_message(message)
            
        except Exception as e:
            logger.error(f"Error processing webhook payload: {e}")
    
    async def _handle_health_check(self, request: Any) -> Any:
        """Health check endpoint for webhook server."""
        from aiohttp import web
        import json
        
        health = await self.health()
        return web.Response(
            status=200 if health.ok else 503,
            text=json.dumps(health.to_dict()),
            content_type="application/json",
        )
    
    async def _check_new_messages(self) -> None:
        """Check for and process new messages."""
        client = self._get_client()
        
        try:
            # SDK v0.4.7: list() returns ListMessagesResponse with .messages list
            response = client.inboxes.messages.list(self._inbox_id)
            msg_list = response.messages if hasattr(response, 'messages') else response
            
            for msg in msg_list:
                # SDK v0.4.7: Message uses .message_id, not .id
                msg_id = msg.message_id
                
                # Skip already processed
                if msg_id in self._processed_ids:
                    continue
                
                self._processed_ids.add(msg_id)
                
                # SDK v0.4.7: Message uses .from_ (not .from_address)
                sender_raw = getattr(msg, 'from_', '') or ''
                sender_email = extract_email_address(sender_raw)
                
                # Skip auto-replies and blocked senders
                headers = getattr(msg, 'headers', {}) or {}
                if is_auto_reply(headers):
                    logger.debug(f"Skipping auto-reply from {sender_email}")
                    continue
                
                if is_blocked_sender(sender_email):
                    logger.debug(f"Skipping blocked sender: {sender_email}")
                    continue
                
                # Build BotMessage — SDK uses .text / .extracted_text, not .body
                body = getattr(msg, 'extracted_text', '') or getattr(msg, 'text', '') or ''
                
                message = BotMessage(
                    message_id=msg_id,
                    content=body,
                    message_type=MessageType.TEXT,
                    sender=BotUser(
                        user_id=sender_email,
                        username=sender_email,
                        display_name=sender_email.split("@")[0] if sender_email else "unknown",
                    ),
                    channel=BotChannel(
                        channel_id=self._inbox_id,
                        name=self._email_address or self._inbox_id,
                    ),
                    thread_id=getattr(msg, 'thread_id', None),
                    metadata={
                        "subject": getattr(msg, 'subject', ''),
                        "message_id": msg_id,
                        "in_reply_to": getattr(msg, 'in_reply_to', ''),
                    },
                )
                
                await self._handle_message(message)
                
        except Exception as e:
            logger.error(f"AgentMail API error: {e}")
    
    async def _handle_message(self, message: BotMessage) -> None:
        """Handle an incoming email message."""
        # Fire message hooks
        self.fire_message_received(message)
        
        # Check command prefix in subject
        subject = message.metadata.get("subject", "")
        if subject.startswith(self.config.command_prefix):
            command = subject[len(self.config.command_prefix):].split()[0].lower()
            if command in self._command_handlers:
                try:
                    await self._command_handlers[command](message)
                except Exception as e:
                    logger.error(f"Command handler error: {e}")
                return
        
        # Call registered message handlers
        for handler in self._message_handlers:
            try:
                result = handler(message)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Message handler error: {e}")
        
        # Process with agent if available
        if self._agent:
            sender_id = message.sender.user_id if message.sender else "unknown"
            body = message.content
            
            try:
                response = await self._session.chat(
                    self._agent,
                    sender_id,
                    body,
                )
                
                if response:
                    # Reply to sender
                    reply_subject = f"Re: {subject}" if subject else "Re: Your message"
                    await self.send_message(
                        channel_id=sender_id,
                        content={"subject": reply_subject, "body": response},
                        reply_to=message.metadata.get("message_id"),
                        thread_id=message.thread_id,
                    )
            except Exception as e:
                logger.error(f"Agent processing error: {e}")
    
    async def send_message(
        self,
        channel_id: str,
        content: Union[str, Dict[str, Any]],
        reply_to: Optional[str] = None,
        thread_id: Optional[str] = None,
        **kwargs,
    ) -> BotMessage:
        """Send an email message.
        
        Args:
            channel_id: Recipient email address
            content: Message content (str or {"subject": ..., "body": ...})
            reply_to: Message-ID to reply to
            thread_id: Thread ID for conversation tracking
            
        Returns:
            The sent message
        """
        # Parse content
        if isinstance(content, dict):
            subject = content.get("subject", "Message from PraisonAI")
            body = content.get("body", "")
        else:
            subject = "Message from PraisonAI"
            body = str(content)
        
        # Fire sending hook
        self.fire_message_sending(channel_id, body)
        
        client = self._get_client()
        
        # Send via AgentMail API
        # SDK v0.4.7: uses text= (not body=); reply_to= is Reply-To header
        # For replying to a message, use messages.reply() method
        try:
            if reply_to:
                # reply_to contains the original message_id — use reply() method
                result = client.inboxes.messages.reply(
                    self._inbox_id,
                    reply_to,  # message_id of original message
                    text=body,
                    subject=subject,
                )
            else:
                result = client.inboxes.messages.send(
                    self._inbox_id,
                    to=channel_id,
                    subject=subject,
                    text=body,
                )
            # SendMessageResponse has .message_id
            message_id = getattr(result, 'message_id', str(uuid.uuid4()))
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            raise
        
        # Build response message
        bot_message = BotMessage(
            message_id=message_id,
            content=body,
            message_type=MessageType.TEXT,
            sender=self._bot_user,
            channel=BotChannel(channel_id=channel_id, name=channel_id),
            reply_to=reply_to,
            thread_id=thread_id,
            metadata={"subject": subject},
        )
        
        # Fire sent hook
        self.fire_message_sent(channel_id, body, message_id)
        
        return bot_message
    
    async def edit_message(
        self,
        channel_id: str,
        message_id: str,
        content: str,
        **kwargs,
    ) -> BotMessage:
        """Edit a message (not supported for email - sends new message)."""
        logger.warning("Email does not support message editing. Sending new message.")
        return await self.send_message(channel_id, content, **kwargs)
    
    async def delete_message(
        self,
        channel_id: str,
        message_id: str,
        **kwargs,
    ) -> bool:
        """Delete a message (not supported for email)."""
        logger.warning("Email does not support message deletion.")
        return False
    
    def on_message(self, handler: Callable) -> Callable:
        """Register a message handler.
        
        Args:
            handler: Function to call for each message
            
        Returns:
            The handler function
        """
        self._message_handlers.append(handler)
        return handler
    
    def on_command(self, command: str) -> Callable:
        """Register a command handler.
        
        Args:
            command: Command name (without prefix)
            
        Returns:
            Decorator function
        """
        def decorator(handler: Callable) -> Callable:
            self._command_handlers[command.lower()] = handler
            return handler
        return decorator
    
    async def create_inbox(
        self,
        domain: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Create a new inbox programmatically.
        
        Args:
            domain: Custom domain for the inbox
            **kwargs: Additional inbox parameters
            
        Returns:
            Inbox details including id and email_address
        """
        client = self._get_client()
        
        params = {}
        if domain:
            params["domain"] = domain
        params.update(kwargs)
        
        inbox = client.inboxes.create(**params)
        
        # SDK v0.4.7: inbox_id IS the email address
        return {
            "id": inbox.inbox_id,
            "email_address": inbox.inbox_id,
            "display_name": getattr(inbox, "display_name", None),
        }
    
    async def list_inboxes(self) -> List[Dict[str, Any]]:
        """List all inboxes for this API key.
        
        Returns:
            List of inbox details
        """
        client = self._get_client()
        # SDK v0.4.7: list() returns response object with .inboxes list
        result = client.inboxes.list()
        inbox_list = result.inboxes if hasattr(result, 'inboxes') else result
        
        return [
            {
                "id": inbox.inbox_id,
                "email_address": inbox.inbox_id,
                "display_name": getattr(inbox, "display_name", None),
            }
            for inbox in inbox_list
        ]
    
    async def delete_inbox(self, inbox_id: str) -> bool:
        """Delete an inbox.
        
        Args:
            inbox_id: ID of inbox to delete
            
        Returns:
            True if deleted successfully
        """
        client = self._get_client()
        
        try:
            client.inboxes.delete(inbox_id)
            return True
        except Exception as e:
            logger.error(f"Failed to delete inbox: {e}")
            return False
    
    async def probe(self) -> ProbeResult:
        """Test AgentMail API connectivity."""
        start_time = time.time()
        
        try:
            client = self._get_client()
            # Test by listing inboxes
            client.inboxes.list()
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            return ProbeResult(
                ok=True,
                platform="agentmail",
                elapsed_ms=elapsed_ms,
                bot_username=self._email_address,
            )
        except ImportError:
            return ProbeResult(
                ok=False,
                platform="agentmail",
                error="agentmail package not installed",
            )
        except Exception as e:
            return ProbeResult(
                ok=False,
                platform="agentmail",
                error=str(e),
            )
    
    async def health(self) -> HealthResult:
        """Get health status of the AgentMail bot."""
        probe_result = await self.probe()
        
        uptime = 0.0
        if self._started_at:
            uptime = time.time() - self._started_at
        
        return HealthResult(
            ok=self._is_running and probe_result.ok,
            platform="agentmail",
            is_running=self._is_running,
            uptime_seconds=uptime,
            probe=probe_result,
            sessions=self._session.active_count() if hasattr(self._session, 'active_count') else 0,
        )
