"""
Slack Bot implementation for PraisonAI.

Provides a full Slack bot runtime with slash commands,
event handling, and agent integration.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from praisonaiagents import Agent

from praisonaiagents.bots import (
    BotConfig,
    BotMessage,
    BotUser,
    BotChannel,
    MessageType,
)

from .media import split_media_from_output, is_audio_file

logger = logging.getLogger(__name__)


class SlackBot:
    """Slack bot runtime for PraisonAI agents.
    
    Connects an agent to Slack, handling messages, slash commands,
    and providing full bot functionality.
    
    Example:
        from praisonai.bots import SlackBot
        from praisonaiagents import Agent
        
        agent = Agent(name="assistant")
        bot = SlackBot(
            token="xoxb-YOUR-BOT-TOKEN",
            app_token="xapp-YOUR-APP-TOKEN",
            agent=agent,
        )
        
        @bot.on_command("help")
        async def help_command(message):
            await bot.send_message(message.channel.channel_id, "Help text...")
        
        await bot.start()
    
    Requires: pip install slack-bolt
    """
    
    def __init__(
        self,
        token: str,
        app_token: Optional[str] = None,
        signing_secret: Optional[str] = None,
        agent: Optional["Agent"] = None,
        config: Optional[BotConfig] = None,
    ):
        """Initialize the Slack bot.
        
        Args:
            token: Slack bot token (xoxb-...)
            app_token: Slack app token for Socket Mode (xapp-...)
            signing_secret: Signing secret for webhook verification
            agent: Optional agent to handle messages
            config: Optional bot configuration
        """
        self._token = token
        self._app_token = app_token
        self._signing_secret = signing_secret
        self._agent = agent
        self.config = config or BotConfig(token=token)
        
        self._is_running = False
        self._bot_user: Optional[BotUser] = None
        self._app = None
        self._client = None
        
        self._message_handlers: List[Callable] = []
        self._command_handlers: Dict[str, Callable] = {}
        
        # Audio capabilities
        self._stt_enabled: bool = False
    
    def enable_stt(self, enabled: bool = True) -> None:
        """Enable STT for audio file transcription."""
        self._stt_enabled = enabled
    
    @property
    def is_running(self) -> bool:
        return self._is_running
    
    @property
    def platform(self) -> str:
        return "slack"
    
    @property
    def bot_user(self) -> Optional[BotUser]:
        return self._bot_user
    
    async def start(self) -> None:
        """Start the Slack bot."""
        if self._is_running:
            logger.warning("Bot already running")
            return
        
        try:
            from slack_bolt.async_app import AsyncApp
            from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
            from slack_sdk.web.async_client import AsyncWebClient
        except ImportError:
            raise ImportError(
                "SlackBot requires slack-bolt. "
                "Install with: pip install slack-bolt"
            )
        
        self._app = AsyncApp(
            token=self._token,
            signing_secret=self._signing_secret,
        )
        self._client = AsyncWebClient(token=self._token)
        
        auth_response = await self._client.auth_test()
        self._bot_user = BotUser(
            user_id=auth_response["user_id"],
            username=auth_response["user"],
            display_name=auth_response.get("bot_id", auth_response["user"]),
            is_bot=True,
        )
        
        @self._app.event("message")
        async def handle_message(event, say):
            if event.get("bot_id"):
                return
            
            bot_message = self._convert_event_to_message(event)
            
            if not self.config.is_user_allowed(bot_message.sender.user_id if bot_message.sender else ""):
                return
            if not self.config.is_channel_allowed(bot_message.channel.channel_id if bot_message.channel else ""):
                return
            
            for handler in self._message_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(bot_message)
                    else:
                        handler(bot_message)
                except Exception as e:
                    logger.error(f"Message handler error: {e}")
            
            should_respond = False
            text = event.get("text", "")
            channel_type = event.get("channel_type", "")
            
            if channel_type == "im":
                should_respond = True
            elif self._bot_user and f"<@{self._bot_user.user_id}>" in text:
                should_respond = True
                text = text.replace(f"<@{self._bot_user.user_id}>", "").strip()
            elif not self.config.mention_required:
                should_respond = True
            
            if should_respond and self._agent:
                try:
                    logger.info(f"Message received: {text[:100]}...")
                    # Run sync agent.chat() in executor to avoid asyncio.run() conflicts
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(None, self._agent.chat, text)
                    logger.info(f"Response sent: {response[:100]}...")
                    
                    # Determine if we should reply in thread
                    thread_ts = None
                    if self.config.reply_in_thread:
                        thread_ts = event.get("thread_ts") or event.get("ts")
                    elif self.config.thread_threshold > 0 and len(response) > self.config.thread_threshold:
                        # Auto-thread long responses
                        thread_ts = event.get("thread_ts") or event.get("ts")
                    
                    await self._send_response_with_media(
                        event.get("channel"), say, response, thread_ts=thread_ts
                    )
                except Exception as e:
                    logger.error(f"Agent error: {e}")
                    error_msg = str(e)
                    if error_msg:
                        await say(text=f"Error: {error_msg}", thread_ts=event.get("ts"))
        
        @self._app.event("app_mention")
        async def handle_mention(event, say):
            if event.get("bot_id"):
                return
            
            text = event.get("text", "")
            if self._bot_user:
                text = text.replace(f"<@{self._bot_user.user_id}>", "").strip()
            
            if self._agent:
                try:
                    logger.info(f"@mention received: {text[:100]}...")
                    # Run sync agent.chat() in executor to avoid asyncio.run() conflicts
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(None, self._agent.chat, text)
                    logger.info(f"Response sent: {response[:100]}...")
                    
                    # Determine if we should reply in thread
                    thread_ts = None
                    if self.config.reply_in_thread:
                        thread_ts = event.get("thread_ts") or event.get("ts")
                    elif self.config.thread_threshold > 0 and len(response) > self.config.thread_threshold:
                        # Auto-thread long responses
                        thread_ts = event.get("thread_ts") or event.get("ts")
                    
                    await self._send_response_with_media(
                        event.get("channel"), say, response, thread_ts=thread_ts
                    )
                except Exception as e:
                    logger.error(f"Agent error: {e}")
                    error_msg = str(e)
                    if error_msg:
                        await say(text=f"Error: {error_msg}", thread_ts=event.get("ts"))
        
        for command, handler in self._command_handlers.items():
            @self._app.command(f"/{command}")
            async def handle_command(ack, command_data, respond, cmd=command, hdlr=handler):
                await ack()
                bot_message = BotMessage(
                    message_id=command_data.get("trigger_id", ""),
                    content=command_data.get("text", ""),
                    message_type=MessageType.COMMAND,
                    sender=BotUser(
                        user_id=command_data.get("user_id", ""),
                        username=command_data.get("user_name", ""),
                    ),
                    channel=BotChannel(
                        channel_id=command_data.get("channel_id", ""),
                        name=command_data.get("channel_name", ""),
                    ),
                )
                try:
                    if asyncio.iscoroutinefunction(hdlr):
                        await hdlr(bot_message)
                    else:
                        hdlr(bot_message)
                except Exception as e:
                    logger.error(f"Command handler error: {e}")
                    await respond(f"Error: {str(e)}")
        
        self._is_running = True
        logger.info(f"Slack bot started: {self._bot_user.username}")
        
        if self._app_token:
            handler = AsyncSocketModeHandler(self._app, self._app_token)
            await handler.start_async()
        else:
            logger.warning("No app_token provided, bot will not receive events via Socket Mode")
    
    async def stop(self) -> None:
        """Stop the Slack bot."""
        if not self._is_running:
            return
        
        self._is_running = False
        logger.info("Slack bot stopped")
    
    def set_agent(self, agent: "Agent") -> None:
        """Set the agent that handles messages."""
        self._agent = agent
    
    def get_agent(self) -> Optional["Agent"]:
        """Get the current agent."""
        return self._agent
    
    async def send_message(
        self,
        channel_id: str,
        content: Union[str, Dict[str, Any]],
        reply_to: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> BotMessage:
        """Send a message to a channel."""
        if not self._client:
            raise RuntimeError("Bot not started")
        
        text = content if isinstance(content, str) else str(content)
        
        kwargs = {"channel": channel_id, "text": text}
        if thread_id:
            kwargs["thread_ts"] = thread_id
        
        response = await self._client.chat_postMessage(**kwargs)
        
        return BotMessage(
            message_id=response["ts"],
            content=text,
            message_type=MessageType.TEXT,
            channel=BotChannel(channel_id=channel_id),
        )
    
    async def _send_long_message(self, say, text: str, thread_ts: Optional[str] = None) -> None:
        """Send a long message, splitting if necessary."""
        max_len = min(self.config.max_message_length, 4000)
        
        if not text or not text.strip():
            logger.warning("Attempted to send empty message")
            return

        if len(text) <= max_len:
            await say(text=text.strip(), thread_ts=thread_ts)
        else:
            chunks = [text[i:i+max_len] for i in range(0, len(text), max_len)]
            for chunk in chunks:
                if chunk and chunk.strip():
                    await say(text=chunk.strip(), thread_ts=thread_ts)
    
    async def _send_response_with_media(
        self,
        channel_id: str,
        say,
        response: str,
        thread_ts: Optional[str] = None,
    ) -> None:
        """Send response, extracting and uploading any MEDIA: files."""
        # Parse response for media
        parsed = split_media_from_output(response)
        text = parsed["text"]
        media_urls = parsed.get("media_urls", [])
        
        # Send text first if present
        if text:
            await self._send_long_message(say, text, thread_ts=thread_ts)
        
        # Upload audio files to Slack
        for media_path in media_urls:
            if not os.path.exists(media_path):
                logger.warning(f"Media file not found: {media_path}")
                continue
            
            if is_audio_file(media_path) and self._client:
                try:
                    # Upload file to Slack
                    await self._client.files_upload_v2(
                        channel=channel_id,
                        file=media_path,
                        title=os.path.basename(media_path),
                        thread_ts=thread_ts,
                    )
                except Exception as e:
                    logger.error(f"Failed to upload audio to Slack: {e}")
    
    async def edit_message(
        self,
        channel_id: str,
        message_id: str,
        content: Union[str, Dict[str, Any]],
    ) -> BotMessage:
        """Edit an existing message."""
        if not self._client:
            raise RuntimeError("Bot not started")
        
        text = content if isinstance(content, str) else str(content)
        
        await self._client.chat_update(
            channel=channel_id,
            ts=message_id,
            text=text,
        )
        
        return BotMessage(
            message_id=message_id,
            content=text,
            message_type=MessageType.EDIT,
            channel=BotChannel(channel_id=channel_id),
        )
    
    async def delete_message(
        self,
        channel_id: str,
        message_id: str,
    ) -> bool:
        """Delete a message."""
        if not self._client:
            raise RuntimeError("Bot not started")
        
        try:
            await self._client.chat_delete(
                channel=channel_id,
                ts=message_id,
            )
            return True
        except Exception as e:
            logger.error(f"Delete message error: {e}")
            return False
    
    def on_message(self, handler: Callable[[BotMessage], Any]) -> Callable:
        """Register a message handler."""
        self._message_handlers.append(handler)
        return handler
    
    def on_command(self, command: str) -> Callable:
        """Decorator to register a command handler."""
        def decorator(func: Callable) -> Callable:
            self._command_handlers[command] = func
            return func
        return decorator
    
    async def send_typing(self, channel_id: str) -> None:
        """Send typing indicator (not supported in Slack API)."""
        pass
    
    async def get_user(self, user_id: str) -> Optional[BotUser]:
        """Get user information."""
        if not self._client:
            return None
        
        try:
            response = await self._client.users_info(user=user_id)
            user = response["user"]
            return BotUser(
                user_id=user["id"],
                username=user.get("name"),
                display_name=user.get("real_name") or user.get("name"),
                is_bot=user.get("is_bot", False),
            )
        except Exception:
            return None
    
    async def get_channel(self, channel_id: str) -> Optional[BotChannel]:
        """Get channel information."""
        if not self._client:
            return None
        
        try:
            response = await self._client.conversations_info(channel=channel_id)
            channel = response["channel"]
            channel_type = "dm" if channel.get("is_im") else "channel"
            return BotChannel(
                channel_id=channel["id"],
                name=channel.get("name"),
                channel_type=channel_type,
            )
        except Exception:
            return None
    
    def _convert_event_to_message(self, event: Dict[str, Any]) -> BotMessage:
        """Convert Slack event to BotMessage."""
        sender = BotUser(
            user_id=event.get("user", ""),
            username=event.get("user", ""),
        )
        
        channel_type = "dm" if event.get("channel_type") == "im" else "channel"
        channel = BotChannel(
            channel_id=event.get("channel", ""),
            channel_type=channel_type,
        )
        
        text = event.get("text", "")
        msg_type = MessageType.TEXT
        
        return BotMessage(
            message_id=event.get("ts", ""),
            content=text,
            message_type=msg_type,
            sender=sender,
            channel=channel,
            timestamp=float(event.get("ts", "0").split(".")[0]) if event.get("ts") else 0,
            thread_id=event.get("thread_ts"),
        )
