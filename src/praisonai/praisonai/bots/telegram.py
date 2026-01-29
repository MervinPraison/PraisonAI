"""
Telegram Bot implementation for PraisonAI.

Provides a full Telegram bot runtime with webhook/polling support,
command handling, and agent integration.
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


class TelegramBot:
    """Telegram bot runtime for PraisonAI agents.
    
    Connects an agent to Telegram, handling messages, commands,
    and providing full bot functionality.
    
    Example:
        from praisonai.bots import TelegramBot
        from praisonaiagents import Agent
        
        agent = Agent(name="assistant")
        bot = TelegramBot(token="YOUR_BOT_TOKEN", agent=agent)
        
        @bot.on_command("help")
        async def help_command(message):
            await bot.send_message(message.channel.channel_id, "Help text...")
        
        await bot.start()
    
    Requires: pip install python-telegram-bot
    """
    
    def __init__(
        self,
        token: str,
        agent: Optional["Agent"] = None,
        config: Optional[BotConfig] = None,
    ):
        """Initialize the Telegram bot.
        
        Args:
            token: Telegram bot token from @BotFather
            agent: Optional agent to handle messages
            config: Optional bot configuration
        """
        self._token = token
        self._agent = agent
        self.config = config or BotConfig(token=token)
        
        self._is_running = False
        self._bot_user: Optional[BotUser] = None
        self._application = None
        
        self._message_handlers: List[Callable] = []
        self._command_handlers: Dict[str, Callable] = {}
    
    @property
    def is_running(self) -> bool:
        return self._is_running
    
    @property
    def platform(self) -> str:
        return "telegram"
    
    @property
    def bot_user(self) -> Optional[BotUser]:
        return self._bot_user
    
    async def start(self) -> None:
        """Start the Telegram bot."""
        if self._is_running:
            logger.warning("Bot already running")
            return
        
        try:
            from telegram import Update
            from telegram.ext import (
                Application,
                CommandHandler,
                MessageHandler,
                filters,
                ContextTypes,
            )
        except ImportError:
            raise ImportError(
                "TelegramBot requires python-telegram-bot. "
                "Install with: pip install python-telegram-bot"
            )
        
        self._application = Application.builder().token(self._token).build()
        
        bot_info = await self._application.bot.get_me()
        self._bot_user = BotUser(
            user_id=str(bot_info.id),
            username=bot_info.username,
            display_name=bot_info.first_name,
            is_bot=True,
        )
        
        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message or not update.message.text:
                return
            
            message = self._convert_update_to_message(update)
            
            if not self.config.is_user_allowed(message.sender.user_id if message.sender else ""):
                return
            if not self.config.is_channel_allowed(message.channel.channel_id if message.channel else ""):
                return
            
            for handler in self._message_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(message)
                    else:
                        handler(message)
                except Exception as e:
                    logger.error(f"Message handler error: {e}")
            
            if self._agent and not message.is_command:
                if self.config.typing_indicator:
                    await update.message.chat.send_action("typing")
                
                try:
                    response = self._agent.chat(message.text)
                    await self._send_long_message(
                        update.message.chat_id,
                        response,
                        reply_to=update.message.message_id,
                    )
                except Exception as e:
                    logger.error(f"Agent error: {e}")
                    await update.message.reply_text(f"Error: {str(e)}")
        
        async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message or not update.message.text:
                return
            
            message = self._convert_update_to_message(update)
            command = message.command
            
            if command and command in self._command_handlers:
                handler = self._command_handlers[command]
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(message)
                    else:
                        handler(message)
                except Exception as e:
                    logger.error(f"Command handler error: {e}")
        
        for command in self._command_handlers:
            self._application.add_handler(CommandHandler(command, handle_command))
        
        self._application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
        )
        
        self._is_running = True
        logger.info(f"Telegram bot started: @{self._bot_user.username}")
        
        if self.config.is_webhook_mode:
            await self._application.run_webhook(
                listen="0.0.0.0",
                port=8443,
                url_path=self.config.webhook_path,
                webhook_url=f"{self.config.webhook_url}{self.config.webhook_path}",
            )
        else:
            await self._application.run_polling(
                poll_interval=self.config.polling_interval,
            )
    
    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if not self._is_running:
            return
        
        self._is_running = False
        
        if self._application:
            await self._application.stop()
            await self._application.shutdown()
        
        logger.info("Telegram bot stopped")
    
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
        if not self._application:
            raise RuntimeError("Bot not started")
        
        text = content if isinstance(content, str) else str(content)
        
        kwargs = {"chat_id": int(channel_id), "text": text}
        if reply_to:
            kwargs["reply_to_message_id"] = int(reply_to)
        if thread_id:
            kwargs["message_thread_id"] = int(thread_id)
        
        sent = await self._application.bot.send_message(**kwargs)
        
        return BotMessage(
            message_id=str(sent.message_id),
            content=text,
            message_type=MessageType.TEXT,
            channel=BotChannel(channel_id=channel_id),
        )
    
    async def _send_long_message(
        self,
        chat_id: int,
        text: str,
        reply_to: Optional[int] = None,
    ) -> None:
        """Send a long message, splitting if necessary."""
        max_len = self.config.max_message_length
        
        if len(text) <= max_len:
            kwargs = {"chat_id": chat_id, "text": text}
            if reply_to:
                kwargs["reply_to_message_id"] = reply_to
            await self._application.bot.send_message(**kwargs)
        else:
            chunks = [text[i:i+max_len] for i in range(0, len(text), max_len)]
            for i, chunk in enumerate(chunks):
                kwargs = {"chat_id": chat_id, "text": chunk}
                if i == 0 and reply_to:
                    kwargs["reply_to_message_id"] = reply_to
                await self._application.bot.send_message(**kwargs)
    
    async def edit_message(
        self,
        channel_id: str,
        message_id: str,
        content: Union[str, Dict[str, Any]],
    ) -> BotMessage:
        """Edit an existing message."""
        if not self._application:
            raise RuntimeError("Bot not started")
        
        text = content if isinstance(content, str) else str(content)
        
        await self._application.bot.edit_message_text(
            chat_id=int(channel_id),
            message_id=int(message_id),
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
        if not self._application:
            raise RuntimeError("Bot not started")
        
        try:
            await self._application.bot.delete_message(
                chat_id=int(channel_id),
                message_id=int(message_id),
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
        """Send typing indicator."""
        if self._application:
            await self._application.bot.send_chat_action(
                chat_id=int(channel_id),
                action="typing",
            )
    
    async def get_user(self, user_id: str) -> Optional[BotUser]:
        """Get user information."""
        if not self._application:
            return None
        
        try:
            chat = await self._application.bot.get_chat(int(user_id))
            return BotUser(
                user_id=str(chat.id),
                username=chat.username,
                display_name=chat.first_name,
                is_bot=False,
            )
        except Exception:
            return None
    
    async def get_channel(self, channel_id: str) -> Optional[BotChannel]:
        """Get channel information."""
        if not self._application:
            return None
        
        try:
            chat = await self._application.bot.get_chat(int(channel_id))
            channel_type = "dm" if chat.type == "private" else chat.type
            return BotChannel(
                channel_id=str(chat.id),
                name=chat.title or chat.username,
                channel_type=channel_type,
            )
        except Exception:
            return None
    
    def _convert_update_to_message(self, update) -> BotMessage:
        """Convert Telegram Update to BotMessage."""
        msg = update.message
        
        sender = BotUser(
            user_id=str(msg.from_user.id),
            username=msg.from_user.username,
            display_name=msg.from_user.first_name,
            is_bot=msg.from_user.is_bot,
        ) if msg.from_user else None
        
        channel_type = "dm" if msg.chat.type == "private" else msg.chat.type
        channel = BotChannel(
            channel_id=str(msg.chat.id),
            name=msg.chat.title or msg.chat.username,
            channel_type=channel_type,
        )
        
        msg_type = MessageType.COMMAND if msg.text and msg.text.startswith("/") else MessageType.TEXT
        
        return BotMessage(
            message_id=str(msg.message_id),
            content=msg.text or "",
            message_type=msg_type,
            sender=sender,
            channel=channel,
            timestamp=msg.date.timestamp() if msg.date else 0,
            thread_id=str(msg.message_thread_id) if msg.message_thread_id else None,
        )
