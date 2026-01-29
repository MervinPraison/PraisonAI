"""
Discord Bot implementation for PraisonAI.

Provides a full Discord bot runtime with slash commands,
message handling, and agent integration.
"""

from __future__ import annotations

import asyncio
import logging
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

logger = logging.getLogger(__name__)


class DiscordBot:
    """Discord bot runtime for PraisonAI agents.
    
    Connects an agent to Discord, handling messages, slash commands,
    and providing full bot functionality.
    
    Example:
        from praisonai.bots import DiscordBot
        from praisonaiagents import Agent
        
        agent = Agent(name="assistant")
        bot = DiscordBot(token="YOUR_BOT_TOKEN", agent=agent)
        
        @bot.on_command("help")
        async def help_command(message):
            await bot.send_message(message.channel.channel_id, "Help text...")
        
        await bot.start()
    
    Requires: pip install discord.py
    """
    
    def __init__(
        self,
        token: str,
        agent: Optional["Agent"] = None,
        config: Optional[BotConfig] = None,
    ):
        """Initialize the Discord bot.
        
        Args:
            token: Discord bot token
            agent: Optional agent to handle messages
            config: Optional bot configuration
        """
        self._token = token
        self._agent = agent
        self.config = config or BotConfig(token=token)
        
        self._is_running = False
        self._bot_user: Optional[BotUser] = None
        self._client = None
        
        self._message_handlers: List[Callable] = []
        self._command_handlers: Dict[str, Callable] = {}
    
    @property
    def is_running(self) -> bool:
        return self._is_running
    
    @property
    def platform(self) -> str:
        return "discord"
    
    @property
    def bot_user(self) -> Optional[BotUser]:
        return self._bot_user
    
    async def start(self) -> None:
        """Start the Discord bot."""
        if self._is_running:
            logger.warning("Bot already running")
            return
        
        try:
            import discord
            from discord.ext import commands
        except ImportError:
            raise ImportError(
                "DiscordBot requires discord.py. "
                "Install with: pip install discord.py"
            )
        
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        
        self._client = commands.Bot(
            command_prefix=self.config.command_prefix,
            intents=intents,
        )
        
        @self._client.event
        async def on_ready():
            self._bot_user = BotUser(
                user_id=str(self._client.user.id),
                username=self._client.user.name,
                display_name=self._client.user.display_name,
                is_bot=True,
            )
            self._is_running = True
            logger.info(f"Discord bot started: {self._client.user.name}")
        
        @self._client.event
        async def on_message(message):
            if message.author.bot:
                return
            
            bot_message = self._convert_message(message)
            
            if not self.config.is_user_allowed(bot_message.sender.user_id if bot_message.sender else ""):
                return
            if not self.config.is_channel_allowed(bot_message.channel.channel_id if bot_message.channel else ""):
                return
            
            if bot_message.is_command:
                command = bot_message.command
                if command and command in self._command_handlers:
                    handler = self._command_handlers[command]
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(bot_message)
                        else:
                            handler(bot_message)
                    except Exception as e:
                        logger.error(f"Command handler error: {e}")
                return
            
            should_respond = False
            if message.guild is None:
                should_respond = True
            elif self._client.user.mentioned_in(message) or not self.config.mention_required:
                should_respond = True
            
            if should_respond:
                for handler in self._message_handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(bot_message)
                        else:
                            handler(bot_message)
                    except Exception as e:
                        logger.error(f"Message handler error: {e}")
                
                if self._agent:
                    if self.config.typing_indicator:
                        async with message.channel.typing():
                            try:
                                response = self._agent.chat(bot_message.text)
                                await self._send_long_message(message.channel, response, reference=message)
                            except Exception as e:
                                logger.error(f"Agent error: {e}")
                                await message.reply(f"Error: {str(e)}")
                    else:
                        try:
                            response = self._agent.chat(bot_message.text)
                            await self._send_long_message(message.channel, response, reference=message)
                        except Exception as e:
                            logger.error(f"Agent error: {e}")
                            await message.reply(f"Error: {str(e)}")
        
        await self._client.start(self._token)
    
    async def stop(self) -> None:
        """Stop the Discord bot."""
        if not self._is_running:
            return
        
        self._is_running = False
        
        if self._client:
            await self._client.close()
        
        logger.info("Discord bot stopped")
    
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
        channel = self._client.get_channel(int(channel_id))
        
        if not channel:
            raise ValueError(f"Channel not found: {channel_id}")
        
        if thread_id:
            thread = channel.get_thread(int(thread_id))
            if thread:
                channel = thread
        
        sent = await channel.send(text)
        
        return BotMessage(
            message_id=str(sent.id),
            content=text,
            message_type=MessageType.TEXT,
            channel=BotChannel(channel_id=channel_id),
        )
    
    async def _send_long_message(self, channel, text: str, reference=None) -> None:
        """Send a long message, splitting if necessary."""
        max_len = min(self.config.max_message_length, 2000)
        
        if len(text) <= max_len:
            if reference:
                await channel.send(text, reference=reference)
            else:
                await channel.send(text)
        else:
            chunks = [text[i:i+max_len] for i in range(0, len(text), max_len)]
            for i, chunk in enumerate(chunks):
                if i == 0 and reference:
                    await channel.send(chunk, reference=reference)
                else:
                    await channel.send(chunk)
    
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
        channel = self._client.get_channel(int(channel_id))
        
        if not channel:
            raise ValueError(f"Channel not found: {channel_id}")
        
        message = await channel.fetch_message(int(message_id))
        await message.edit(content=text)
        
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
            channel = self._client.get_channel(int(channel_id))
            if channel:
                message = await channel.fetch_message(int(message_id))
                await message.delete()
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
        """Send typing indicator."""
        if self._client:
            channel = self._client.get_channel(int(channel_id))
            if channel:
                await channel.trigger_typing()
    
    async def get_user(self, user_id: str) -> Optional[BotUser]:
        """Get user information."""
        if not self._client:
            return None
        
        try:
            user = await self._client.fetch_user(int(user_id))
            return BotUser(
                user_id=str(user.id),
                username=user.name,
                display_name=user.display_name,
                is_bot=user.bot,
            )
        except Exception:
            return None
    
    async def get_channel(self, channel_id: str) -> Optional[BotChannel]:
        """Get channel information."""
        if not self._client:
            return None
        
        try:
            channel = self._client.get_channel(int(channel_id))
            if channel:
                channel_type = "dm" if hasattr(channel, "recipient") else "channel"
                return BotChannel(
                    channel_id=str(channel.id),
                    name=getattr(channel, "name", None),
                    channel_type=channel_type,
                )
        except Exception:
            pass
        return None
    
    def _convert_message(self, message) -> BotMessage:
        """Convert Discord Message to BotMessage."""
        sender = BotUser(
            user_id=str(message.author.id),
            username=message.author.name,
            display_name=message.author.display_name,
            is_bot=message.author.bot,
        )
        
        channel_type = "dm" if message.guild is None else "channel"
        channel = BotChannel(
            channel_id=str(message.channel.id),
            name=getattr(message.channel, "name", None),
            channel_type=channel_type,
        )
        
        content = message.content
        if self._client and self._client.user:
            content = content.replace(f"<@{self._client.user.id}>", "").strip()
            content = content.replace(f"<@!{self._client.user.id}>", "").strip()
        
        msg_type = MessageType.COMMAND if content.startswith(self.config.command_prefix) else MessageType.TEXT
        
        return BotMessage(
            message_id=str(message.id),
            content=content,
            message_type=msg_type,
            sender=sender,
            channel=channel,
            timestamp=message.created_at.timestamp() if message.created_at else 0,
            thread_id=str(message.thread.id) if hasattr(message, "thread") and message.thread else None,
        )
