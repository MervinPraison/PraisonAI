"""
Email Bot implementation for PraisonAI.

Provides an email bot runtime with IMAP polling and SMTP sending,
command handling, and agent integration.

Requires: pip install praisonai[email]
"""

from __future__ import annotations

import asyncio
import email
import email.utils
import hashlib
import imaplib
import logging
import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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
from ._email_utils import is_auto_reply, is_blocked_sender

logger = logging.getLogger(__name__)


class EmailBot(ChatCommandMixin, MessageHookMixin):
    """Email bot runtime for PraisonAI agents.
    
    Connects an agent to email via IMAP/SMTP, handling incoming emails
    as messages and sending replies.
    
    Example:
        from praisonai.bots import EmailBot
        from praisonaiagents import Agent
        
        agent = Agent(name="email_assistant")
        bot = EmailBot(
            token="app_password",  # Gmail app password
            email_address="bot@example.com",
            imap_server="imap.gmail.com",
            smtp_server="smtp.gmail.com",
            agent=agent,
        )
        
        await bot.start()
    
    Environment variables (if not passed directly):
        EMAIL_APP_PASSWORD: App password for authentication
        EMAIL_ADDRESS: Email address for the bot
        EMAIL_IMAP_SERVER: IMAP server (default: imap.gmail.com)
        EMAIL_SMTP_SERVER: SMTP server (default: smtp.gmail.com)
    """
    
    def __init__(
        self,
        token: str,
        agent: Optional["Agent"] = None,
        config: Optional[BotConfig] = None,
        email_address: Optional[str] = None,
        imap_server: Optional[str] = None,
        smtp_server: Optional[str] = None,
        imap_port: int = 993,
        smtp_port: int = 587,
        **kwargs,
    ):
        """Initialize the Email bot.
        
        Args:
            token: App password for email authentication
            agent: Optional agent to handle messages
            config: Optional bot configuration
            email_address: Bot's email address (or EMAIL_ADDRESS env var)
            imap_server: IMAP server hostname (or EMAIL_IMAP_SERVER env var)
            smtp_server: SMTP server hostname (or EMAIL_SMTP_SERVER env var)
            imap_port: IMAP port (default: 993 for SSL)
            smtp_port: SMTP port (default: 587 for STARTTLS)
            **kwargs: Additional arguments for forward compatibility
        """
        self._extra_kwargs = kwargs
        self._token = token
        self._agent = agent
        self.config = config or BotConfig(token=token)
        
        # Email-specific config
        self._email_address = email_address or os.environ.get("EMAIL_ADDRESS", "")
        self._imap_server = imap_server or os.environ.get("EMAIL_IMAP_SERVER", "imap.gmail.com")
        self._smtp_server = smtp_server or os.environ.get("EMAIL_SMTP_SERVER", "smtp.gmail.com")
        self._imap_port = imap_port
        self._smtp_port = smtp_port
        
        self._is_running = False
        self._bot_user: Optional[BotUser] = None
        self._imap: Optional[imaplib.IMAP4_SSL] = None
        
        self._message_handlers: List[Callable] = []
        self._command_handlers: Dict[str, Callable] = {}
        self._started_at: Optional[float] = None
        self._processed_uids: set = set()  # Track processed email UIDs
        
        try:
            from praisonaiagents.session import get_default_session_store
            _store = get_default_session_store()
        except Exception:
            _store = None
        self._session: BotSessionManager = BotSessionManager(
            store=_store,
            platform="email",
        )
        
        self._stop_event: Optional[asyncio.Event] = None
        self._poll_task: Optional[asyncio.Task] = None
    
    @property
    def is_running(self) -> bool:
        return self._is_running
    
    @property
    def platform(self) -> str:
        return "email"
    
    @property
    def bot_user(self) -> Optional[BotUser]:
        return self._bot_user
    
    def set_agent(self, agent: "Agent") -> None:
        """Set the agent that handles messages."""
        self._agent = agent
    
    def get_agent(self) -> Optional["Agent"]:
        """Get the current agent."""
        return self._agent
    
    async def start(self) -> None:
        """Start the Email bot (begin IMAP polling)."""
        if self._is_running:
            logger.warning("EmailBot already running")
            return
        
        if not self._email_address:
            raise ValueError(
                "Email address required. Set EMAIL_ADDRESS env var or pass email_address parameter."
            )
        
        if not self._token:
            raise ValueError(
                "App password required. Set EMAIL_APP_PASSWORD env var or pass token parameter."
            )
        
        # Test connection
        probe = await self.probe()
        if not probe.ok:
            raise ConnectionError(f"Failed to connect to email server: {probe.error}")
        
        self._bot_user = BotUser(
            user_id=self._email_address,
            username=self._email_address,
            display_name=self._email_address.split("@")[0],
            is_bot=True,
        )
        
        self._is_running = True
        self._started_at = time.time()
        self._stop_event = asyncio.Event()
        
        # Start polling loop
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info(f"EmailBot started for {self._email_address}")
    
    async def stop(self) -> None:
        """Stop the Email bot."""
        if not self._is_running:
            return
        
        self._is_running = False
        if self._stop_event:
            self._stop_event.set()
        
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        
        if self._imap:
            try:
                self._imap.logout()
            except Exception:
                pass
            self._imap = None
        
        logger.info("EmailBot stopped")
    
    async def _poll_loop(self) -> None:
        """Main polling loop for checking new emails."""
        poll_interval = self.config.polling_interval or 30.0  # Default 30s for email
        
        while self._is_running:
            try:
                await self._check_new_emails()
            except Exception as e:
                logger.error(f"Error checking emails: {e}")
            
            # Wait for next poll or stop signal
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=poll_interval,
                )
                break  # Stop event was set
            except asyncio.TimeoutError:
                continue  # Normal timeout, continue polling
    
    async def _check_new_emails(self) -> None:
        """Check for new unread emails and process them."""
        loop = asyncio.get_event_loop()
        
        try:
            # Connect to IMAP
            imap = await loop.run_in_executor(
                None,
                lambda: imaplib.IMAP4_SSL(self._imap_server, self._imap_port)
            )
            await loop.run_in_executor(
                None,
                lambda: imap.login(self._email_address, self._token)
            )
            await loop.run_in_executor(None, lambda: imap.select("INBOX"))
            
            # Search for unread emails
            _, message_numbers = await loop.run_in_executor(
                None,
                lambda: imap.search(None, "UNSEEN")
            )
            
            for num in message_numbers[0].split():
                if not self._is_running:
                    break
                
                uid = num.decode()
                if uid in self._processed_uids:
                    continue
                
                try:
                    _, msg_data = await loop.run_in_executor(
                        None,
                        lambda n=num: imap.fetch(n, "(RFC822)")
                    )
                    
                    if msg_data[0] is None:
                        continue
                    
                    raw_email = msg_data[0][1]
                    email_message = email.message_from_bytes(raw_email)
                    
                    # Check for auto-reply headers
                    if self._is_auto_reply(email_message):
                        logger.debug(f"Skipping auto-reply email: {uid}")
                        self._processed_uids.add(uid)
                        continue
                    
                    # Parse sender
                    from_header = email_message.get("From", "")
                    sender_name, sender_email = email.utils.parseaddr(from_header)
                    
                    # Check for blocked senders
                    if self._is_blocked_sender(sender_email):
                        logger.debug(f"Skipping blocked sender: {sender_email}")
                        self._processed_uids.add(uid)
                        continue
                    
                    # Extract body
                    body = self._extract_body(email_message)
                    subject = email_message.get("Subject", "(No Subject)")
                    message_id = email_message.get("Message-ID", uid)
                    references = email_message.get("References", "")
                    in_reply_to = email_message.get("In-Reply-To", "")
                    
                    # Create BotMessage
                    bot_message = BotMessage(
                        message_id=message_id,
                        content=f"Subject: {subject}\n\n{body}",
                        message_type=MessageType.TEXT,
                        sender=BotUser(
                            user_id=sender_email,
                            username=sender_email,
                            display_name=sender_name or sender_email,
                        ),
                        channel=BotChannel(
                            channel_id=sender_email,
                            name=sender_email,
                            channel_type="dm",
                        ),
                        reply_to=in_reply_to or None,
                        thread_id=references or message_id,
                        metadata={
                            "subject": subject,
                            "message_id": message_id,
                            "references": references,
                            "in_reply_to": in_reply_to,
                        },
                    )
                    
                    self._processed_uids.add(uid)
                    
                    # Process message
                    await self._handle_message(bot_message)
                    
                except Exception as e:
                    logger.error(f"Error processing email {uid}: {e}")
            
            await loop.run_in_executor(None, imap.logout)
            
        except Exception as e:
            logger.error(f"IMAP error: {e}")
    
    def _is_auto_reply(self, msg: email.message.Message) -> bool:
        """Check if email is an auto-reply."""
        headers = {k: v for k, v in msg.items()}
        return is_auto_reply(headers)
    
    def _is_blocked_sender(self, sender: str) -> bool:
        """Check if sender should be blocked."""
        return is_blocked_sender(sender)
    
    def _extract_body(self, msg: email.message.Message) -> str:
        """Extract plain text body from email."""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        return payload.decode(charset, errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        return ""
    
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
            try:
                # Extract just the body for the agent
                body = message.content
                if body.startswith("Subject:"):
                    body = body.split("\n\n", 1)[-1]
                
                response = await self._session.chat(
                    self._agent,
                    message.sender.user_id,
                    body,
                )
                
                if response:
                    # Reply to the email
                    await self.send_message(
                        channel_id=message.sender.user_id,
                        content={
                            "subject": f"Re: {message.metadata.get('subject', '')}",
                            "body": response,
                        },
                        reply_to=message.message_id,
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
    ) -> BotMessage:
        """Send an email message.
        
        Args:
            channel_id: Recipient email address
            content: Message content (str or {"subject": ..., "body": ...})
            reply_to: Message-ID to reply to (sets In-Reply-To header)
            thread_id: References chain (sets References header)
            
        Returns:
            The sent message
        """
        # Fire sending hook
        content_str = content.get("body", "") if isinstance(content, dict) else str(content)
        self.fire_message_sending(channel_id, content_str)
        
        # Parse content
        if isinstance(content, dict):
            subject = content.get("subject", "Message from PraisonAI")
            body = content.get("body", "")
            html = content.get("html")
        else:
            subject = "Message from PraisonAI"
            body = str(content)
            html = None
        
        # Build email
        if html:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body, "plain"))
            msg.attach(MIMEText(html, "html"))
        else:
            msg = MIMEText(body, "plain")
        
        msg["From"] = self._email_address
        msg["To"] = channel_id
        msg["Subject"] = subject
        
        # Generate unique Message-ID
        domain = self._email_address.split("@")[-1]
        message_id = f"<{hashlib.md5(f'{time.time()}{channel_id}'.encode()).hexdigest()}@{domain}>"
        msg["Message-ID"] = message_id
        
        # Threading headers
        if reply_to:
            msg["In-Reply-To"] = reply_to
        if thread_id:
            msg["References"] = thread_id
        
        # Add auto-reply header to prevent loops
        msg["X-Auto-Reply"] = "yes"
        msg["Auto-Submitted"] = "auto-replied"
        
        # Send via SMTP
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._send_smtp, msg)
        
        # Create BotMessage for return
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
    
    def _send_smtp(self, msg: MIMEText) -> None:
        """Send email via SMTP (sync, runs in executor)."""
        with smtplib.SMTP(self._smtp_server, self._smtp_port) as server:
            server.starttls()
            server.login(self._email_address, self._token)
            server.send_message(msg)
    
    async def edit_message(
        self,
        channel_id: str,
        message_id: str,
        content: Union[str, Dict[str, Any]],
    ) -> BotMessage:
        """Edit a message (not supported for email - sends new message)."""
        logger.warning("Email does not support message editing. Sending new message.")
        return await self.send_message(channel_id, content)
    
    async def delete_message(self, channel_id: str, message_id: str) -> bool:
        """Delete a message (not supported for email)."""
        logger.warning("Email does not support message deletion.")
        return False
    
    def on_message(self, handler: Callable[[BotMessage], Any]) -> Callable:
        """Register a message handler."""
        self._message_handlers.append(handler)
        return handler
    
    def on_command(self, command: str) -> Callable:
        """Decorator to register a command handler.
        
        Commands are detected from email subject lines starting with
        the command prefix (default: "/").
        
        Example:
            @bot.on_command("status")
            async def handle_status(message):
                await bot.send_message(message.channel.channel_id, "Bot is running!")
        """
        def decorator(func: Callable) -> Callable:
            self._command_handlers[command.lower()] = func
            return func
        return decorator
    
    async def send_typing(self, channel_id: str) -> None:
        """Send typing indicator (no-op for email)."""
        pass
    
    async def get_user(self, user_id: str) -> Optional[BotUser]:
        """Get user information."""
        return BotUser(user_id=user_id, username=user_id)
    
    async def get_channel(self, channel_id: str) -> Optional[BotChannel]:
        """Get channel information."""
        return BotChannel(channel_id=channel_id, name=channel_id, channel_type="dm")
    
    async def probe(self) -> ProbeResult:
        """Test email server connectivity."""
        start_time = time.time()
        
        try:
            loop = asyncio.get_event_loop()
            
            # Test IMAP
            imap = await loop.run_in_executor(
                None,
                lambda: imaplib.IMAP4_SSL(self._imap_server, self._imap_port)
            )
            await loop.run_in_executor(
                None,
                lambda: imap.login(self._email_address, self._token)
            )
            await loop.run_in_executor(None, imap.logout)
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            return ProbeResult(
                ok=True,
                platform="email",
                elapsed_ms=elapsed_ms,
                bot_username=self._email_address,
            )
        except Exception as e:
            return ProbeResult(
                ok=False,
                platform="email",
                error=str(e),
            )
    
    async def health(self) -> HealthResult:
        """Get health status of the email bot."""
        probe_result = await self.probe()
        
        uptime = 0.0
        if self._started_at:
            uptime = time.time() - self._started_at
        
        return HealthResult(
            ok=self._is_running and probe_result.ok,
            platform="email",
            is_running=self._is_running,
            uptime_seconds=uptime,
            probe=probe_result,
            sessions=self._session.active_count() if hasattr(self._session, 'active_count') else 0,
        )
