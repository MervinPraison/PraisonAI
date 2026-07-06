"""
Discord Bot implementation for PraisonAI.

Provides a full Discord bot runtime with slash commands,
message handling, and agent integration.
"""

from __future__ import annotations

import asyncio
import logging
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
    PlatformCapabilities,
)

from ._commands import (
    format_status, 
    format_help, 
    handle_stop_command,
    handle_model_command,
    handle_usage_command,
    handle_compress_command,
    handle_queue_command,
    handle_learn_command,
    handle_undo_command,
    handle_sessions_command,
    handle_resume_command,
    handle_reasoning_command,
    get_last_user_message,
    build_command_access_policy,
)
from ._session import BotSessionManager
from ._debounce import InboundDebouncer
from ._ack import AckReactor
from ._unknown_user import UnknownUserHandler, BotContext
from ._pairing_ui import PairingUIBuilder, PairingCallbackHandler
from ._outbound_resilience import OutboundResilienceMixin
from ..gateway.pairing import PairingStore

logger = logging.getLogger(__name__)


class DiscordBot(OutboundResilienceMixin, ChatCommandMixin, MessageHookMixin):
    """Discord bot runtime for PraisonAI agents.
    
    Connects an agent to Discord, handling messages, slash commands,
    and providing full bot functionality.
    
    Example:
        from praisonai_bot.bots import DiscordBot
        from praisonaiagents import Agent
        
        agent = Agent(name="assistant")
        bot = DiscordBot(token="YOUR_BOT_TOKEN", agent=agent)
        
        @bot.on_command("help")
        async def help_command(message):
            await bot.send_message(message.channel.channel_id, "Help text...")
        
        await bot.start()
    
    Requires: pip install discord.py
    """
    
    _outbound_platform = "discord"
    
    def __init__(
        self,
        token: str,
        agent: Optional["Agent"] = None,
        config: Optional[BotConfig] = None,
        **kwargs,
    ):
        """Initialize the Discord bot.
        
        Args:
            token: Discord bot token
            agent: Optional agent to handle messages
            config: Optional bot configuration
            **kwargs: Additional arguments for forward compatibility
        """
        # B9: Store extra kwargs for forward compatibility
        self._extra_kwargs = kwargs
        self._token = token
        self._agent = agent
        self.config = config or BotConfig(token=token)
        
        # Initialize allow_silence from config
        self._allow_silence = getattr(self.config, 'allow_silence', False)
        
        self._is_running = False
        self._bot_user: Optional[BotUser] = None
        self._client = None
        
        self._message_handlers: List[Callable] = []
        self._command_handlers: Dict[str, Callable] = {}
        self._started_at: Optional[float] = None

        # Per-command authorization, shared with Telegram/Slack so privileged
        # commands (e.g. /learn) can be restricted consistently across channels.
        self._command_policy = build_command_access_policy(self.config)
        # Use helper to build session manager
        from ._session import build_session_manager
        self._session: BotSessionManager = build_session_manager(
            self.config,
            platform="discord"
        )
        self._debouncer: InboundDebouncer = InboundDebouncer(
            debounce_ms=self.config.debounce_ms,
        )
        self._ack: AckReactor = AckReactor(
            ack_emoji=self.config.ack_emoji,
            done_emoji=self.config.done_emoji,
        )
        
        # Pairing system
        self._pairing_store = PairingStore()
        self._pairing_callback_handler = PairingCallbackHandler(self._pairing_store)
        
        # Create adapter-specific registry and register handlers
        from praisonaiagents.bots import create_registry
        self._interactive_registry = create_registry()
        self._register_interactive_handlers()
        self._bot_context: Optional[BotContext] = None
    
    @property
    def is_running(self) -> bool:
        return self._is_running
    
    @property
    def platform(self) -> str:
        return "discord"
    
    @property
    def bot_user(self) -> Optional[BotUser]:
        return self._bot_user
    
    @property
    def capabilities(self) -> Dict[str, Any]:
        """Discord supports edit, reactions, and typing."""
        return {
            "live_edit": True,
            "reactions": True,
            "typing": True,
            "text_limit": 2000,  # Discord message limit
            "edit_rate_limit": 1.0,
            "reaction_rate_limit": 0.25,  # Discord has generous rate limits
        }
    
    @property
    def platform_capabilities(self) -> PlatformCapabilities:
        """Return Discord platform capabilities."""
        return self.default_capabilities()
    
    @classmethod
    def default_capabilities(cls) -> PlatformCapabilities:
        """Default Discord platform capabilities."""
        return PlatformCapabilities(
            max_message_length=2000,  # Discord's limit for regular messages
            length_unit="codepoints",
            supports_edit=True,  # Discord supports message editing
            supports_typing=True,
            markdown_dialect="discord_markdown",
            needs_rate_limit=False,  # Discord.py handles rate limiting
            edit_interval_ms=500,  # Discord is less restrictive on edits
            max_files_per_message=10,
            max_file_size_mb=8,  # Default Discord limit (varies by boost level)
            supported_file_types=["*"],  # Discord supports most file types
        )
    
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
        self._started_at = time.time()
        
        @self._client.event
        async def on_ready():
            self._bot_user = BotUser(
                user_id=str(self._client.user.id),
                username=self._client.user.name,
                display_name=self._client.user.display_name,
                is_bot=True,
            )
            
            # Initialize bot context for pairing system
            self._bot_context = BotContext(
                config=self.config,
                pairing_store=self._pairing_store,
                adapter=self
            )
            
            self._is_running = True
            logger.info(f"Discord bot started: {self._client.user.name}")

            # Project the shared command registry into Discord's native slash
            # menu so typing "/" surfaces the available commands.
            try:
                await self.publish_command_menu(self.build_command_menu_entries())
            except Exception as e:  # noqa: BLE001 — menu is best-effort, never fatal
                logger.debug(f"Failed to publish Discord command menu (non-fatal): {e}")
        
        @self._client.event
        async def on_message(message):
            if message.author.bot:
                return
            
            bot_message = self._convert_message(message)
            
            # Add channel type for pairing system
            bot_message._channel_type = "discord"
            
            if self.fire_message_received(bot_message).get("drop"):
                logger.debug("Message dropped by MESSAGE_RECEIVED hook")
                return
            
            # Check if channel is allowed
            if not self.config.is_channel_allowed(bot_message.channel.channel_id if bot_message.channel else ""):
                return
            
            # Handle unknown users with pairing system
            user_id = bot_message.sender.user_id if bot_message.sender else ""
            is_explicitly_allowed = bool(self.config.allowed_users) and self.config.is_user_allowed(user_id)
            if not is_explicitly_allowed:
                user_allowed = await UnknownUserHandler.handle(bot_message, self._bot_context)
                if not user_allowed:
                    return
            
            if bot_message.is_command:
                command = bot_message.command
                # Per-command authorization: privileged commands (e.g. /learn)
                # can be restricted to admins independent of the channel/pairing
                # allow gate, consistent with Telegram and Slack.
                if command and not self._command_policy.can_run(
                    str(message.author.id), command
                ):
                    await message.reply(
                        f"⛔ You are not permitted to run /{command}"
                    )
                    return
                if command == "status":
                    await message.reply(self._format_status())
                    return
                elif command == "new":
                    user_id = str(message.author.id)
                    # Pass the chat route so a /new in a channel clears the
                    # shared per_chat session (Issue #2376); no-op for per_user.
                    self._session.reset(
                        user_id,
                        account=getattr(self.config, "account", "default"),
                        chat_id=str(message.channel.id),
                    )
                    await message.reply("Session reset. Starting fresh conversation.")
                    return
                elif command == "help":
                    await message.reply(self._format_help())
                    return
                elif command == "stop":
                    user_id = str(message.author.id)
                    response = handle_stop_command(self._session, user_id)
                    await message.reply(response)
                    return
                elif command == "model":
                    user_id = str(message.author.id)
                    # Extract model name from message
                    parts = bot_message.text.split(maxsplit=1)
                    model_name = parts[1] if len(parts) > 1 else None
                    response = handle_model_command(self._session, user_id, model_name, self._agent)
                    await message.reply(response)
                    return
                elif command == "usage":
                    user_id = str(message.author.id)
                    response = handle_usage_command(self._session, user_id, self._agent)
                    await message.reply(response)
                    return
                elif command == "compress":
                    user_id = str(message.author.id)
                    response = handle_compress_command(self._session, user_id, self._agent)
                    await message.reply(response)
                    return
                elif command == "queue":
                    user_id = str(message.author.id)
                    # Extract message text from command
                    parts = bot_message.text.split(maxsplit=1)
                    message_text = parts[1] if len(parts) > 1 else None
                    response = handle_queue_command(self._session, user_id, message_text)
                    await message.reply(response)
                    return
                elif command == "learn":
                    # Extract request text from command
                    parts = bot_message.text.split(maxsplit=1)
                    request = parts[1] if len(parts) > 1 else None
                    response = handle_learn_command(self._agent, request)
                    await message.reply(response)
                    return
                elif command == "undo":
                    response = handle_undo_command(self._agent)
                    await message.reply(response)
                    return
                elif command == "sessions":
                    user_id = str(message.author.id)
                    response = handle_sessions_command(self._session, user_id)
                    await message.reply(response)
                    return
                elif command == "resume":
                    user_id = str(message.author.id)
                    parts = bot_message.text.split(maxsplit=1)
                    session_id = parts[1] if len(parts) > 1 else None
                    response = handle_resume_command(self._session, user_id, session_id)
                    await message.reply(response)
                    return
                elif command == "retry":
                    user_id = str(message.author.id)
                    last_user_msg = get_last_user_message(self._session, user_id)
                    if not last_user_msg:
                        await message.reply(
                            "ℹ️ Nothing to retry — no previous message found."
                        )
                        return
                    await message.reply("🔁 Retrying your last message…")
                    try:
                        response = await self._session.chat(
                            self._agent, user_id, last_user_msg,
                            chat_id=str(message.channel.id),
                            user_name=str(getattr(message.author, "name", "")),
                            message_id=str(message.id),
                            account=getattr(self.config, "account", "default"),
                        )
                        await message.reply(response)
                    except Exception as e:  # noqa: BLE001 - surface a friendly message
                        logger.warning("retry failed: %s", e)
                        await message.reply(f"❌ Retry failed: {e}")
                    return
                elif command == "reasoning":
                    user_id = str(message.author.id)
                    response = handle_reasoning_command(self._session, user_id, self._agent)
                    await message.reply(response)
                    return
                elif command and command in self._command_handlers:
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
                    user_id = str(message.author.id)
                    
                    # Ack reaction - show processing indicator
                    ack_ctx = None
                    if self._ack.enabled:
                        async def _discord_react(emoji, **kw):
                            try:
                                await message.add_reaction(emoji)
                            except Exception:
                                pass  # Reactions may not be supported
                        async def _discord_unreact(emoji, **kw):
                            try:
                                await message.remove_reaction(emoji, self._client.user)
                            except Exception:
                                pass
                        ack_ctx = await self._ack.ack(react_fn=_discord_react)
                    
                    async def _send_agent_response():
                        text_to_send = await self._debouncer.debounce(user_id, bot_message.text)
                        response = await self._session.chat(
                            self._agent, user_id, text_to_send,
                            chat_id=str(message.channel.id),
                            user_name=str(getattr(message.author, "name", "")),
                            message_id=str(message.id),
                            account=getattr(self.config, "account", "default"),
                        )
                        send_result = self.fire_message_sending(
                            str(message.channel.id), str(response),
                        )
                        if send_result["cancel"]:
                            return
                        await self._send_long_message(message.channel, send_result["content"], reference=message)
                        self.fire_message_sent(str(message.channel.id), send_result["content"])
                        # Done reaction - show completion
                        if ack_ctx:
                            await self._ack.done(ack_ctx, react_fn=_discord_react, unreact_fn=_discord_unreact)

                    if self.config.typing_indicator:
                        async with message.channel.typing():
                            try:
                                await _send_agent_response()
                            except Exception as e:
                                logger.error(f"Agent error: {e}")
                                await message.reply(f"Error: {str(e)}")
                    else:
                        try:
                            await _send_agent_response()
                        except Exception as e:
                            logger.error(f"Agent error: {e}")
                            await message.reply(f"Error: {str(e)}")
        
        await self._client.start(self._token)
    
    async def stop(self) -> None:
        """Stop the Discord bot."""
        if not self._is_running:
            return
        
        self._is_running = False
        self._debouncer.cancel_all()
        
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
        
        # Durable delivery: retry transient failures with backoff and park the
        # reply in the outbound DLQ on permanent failure instead of dropping it.
        sent = await self.deliver_outbound(
            lambda: channel.send(text),
            channel_id=channel_id,
            reply_text=text,
            thread_id=thread_id,
            reply_to=reply_to,
        )
        
        return BotMessage(
            message_id=str(sent.id),
            content=text,
            message_type=MessageType.TEXT,
            channel=BotChannel(channel_id=channel_id),
        )
    
    async def _send_long_message(self, channel, text: str, reference=None) -> None:
        """Send a long message, splitting with markdown-aware chunking."""
        from ._chunk import chunk_message

        max_len = min(self.config.max_message_length, 2000)
        
        if len(text) <= max_len:
            if reference:
                await channel.send(text, reference=reference)
            else:
                await channel.send(text)
        else:
            chunks = chunk_message(text, max_length=max_len, preserve_fences=True)
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
    
    async def add_reaction(self, channel_id: str, message_id: str, emoji: str) -> bool:
        """Add a reaction to a message."""
        if not self._client:
            return False
        
        try:
            channel = self._client.get_channel(int(channel_id))
            if channel:
                message = await channel.fetch_message(int(message_id))
                await message.add_reaction(emoji)
                return True
        except Exception as e:
            logger.debug(f"Failed to add reaction: {e}")
        return False
    
    async def remove_reaction(self, channel_id: str, message_id: str, emoji: str) -> bool:
        """Remove a reaction from a message."""
        if not self._client:
            return False
        
        try:
            channel = self._client.get_channel(int(channel_id))
            if channel:
                message = await channel.fetch_message(int(message_id))
                await message.remove_reaction(emoji, self._client.user)
                return True
        except Exception as e:
            logger.debug(f"Failed to remove reaction: {e}")
        return False
    
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
    
    async def probe(self):
        """Test Discord API connectivity without starting the bot."""
        from praisonaiagents.bots import ProbeResult
        started = time.time()
        try:
            import aiohttp
            url = "https://discord.com/api/v10/users/@me"
            headers = {"Authorization": f"Bot {self._token}"}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    elapsed = (time.time() - started) * 1000
                    if resp.status == 200:
                        data = await resp.json()
                        return ProbeResult(
                            ok=True, platform="discord", elapsed_ms=elapsed,
                            bot_username=data.get("username"),
                            details={"bot_id": data.get("id"), "discriminator": data.get("discriminator")},
                        )
                    else:
                        text = await resp.text()
                        return ProbeResult(ok=False, platform="discord", elapsed_ms=elapsed, error=f"HTTP {resp.status}: {text[:200]}")
        except Exception as e:
            return ProbeResult(ok=False, platform="discord", elapsed_ms=(time.time() - started) * 1000, error=str(e))

    async def health(self):
        """Get detailed health status of the Discord bot."""
        return await self._default_health()

    async def publish_command_menu(self, entries: List[tuple]) -> None:
        """Register commands as Discord application commands for ``/`` autocomplete.

        Projects the shared command registry's ``(name, description)`` pairs
        into Discord's native slash-command menu via the client's
        ``CommandTree`` so typing ``/`` shows the available commands with
        descriptions. Each registered command is a thin shim: on invocation it
        replies telling the user the command is recognised, since the existing
        text-command path (``on_message``) remains the execution route. This
        keeps discoverability (the world-class missing piece) additive and
        backward-compatible. Best-effort: any failure is logged and swallowed
        so bot startup is never blocked.

        Args:
            entries: ``(name, description)`` pairs to publish.
        """
        if not entries or self._client is None:
            return

        try:
            import discord
            from discord import app_commands
        except ImportError:
            return

        tree = getattr(self._client, "tree", None)
        if tree is None:
            return

        import re

        prefix = getattr(self.config, "command_prefix", "/") or "/"
        registered = 0
        for name, description in entries:
            if not name:
                continue
            safe_name = str(name).lower()
            if not re.fullmatch(r"[a-z0-9_-]{1,32}", safe_name):
                continue
            desc = (str(description) or "").strip()[:100] or safe_name

            async def _callback(interaction, _name=safe_name, _prefix=prefix):
                try:
                    await interaction.response.send_message(
                        f"Type `{_prefix}{_name}` as a message to run this command.",
                        ephemeral=True,
                    )
                except Exception:  # noqa: BLE001 — never break the interaction
                    pass

            try:
                cmd = app_commands.Command(
                    name=safe_name,
                    description=desc,
                    callback=_callback,
                )
                tree.add_command(cmd, override=True)
                registered += 1
            except Exception as e:  # noqa: BLE001 — skip any bad entry
                logger.debug(f"Could not add Discord command /{safe_name}: {e}")

        if not registered:
            return

        try:
            await tree.sync()
            logger.info(f"Published {registered} commands to Discord slash menu")
        except Exception as e:  # noqa: BLE001 — best-effort
            logger.debug(f"Discord command sync failed (non-fatal): {e}")

    def _format_status(self) -> str:
        """Format /status response."""
        return format_status(self._agent, self.platform, self._started_at, self._is_running)
    
    def _format_help(self) -> str:
        """Format /help response."""
        extra = {cmd: "Custom command" for cmd in self._command_handlers}
        return format_help(self._agent, self.platform, extra)
    
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
    
    # Adapter methods for pairing system
    async def send_approval_dm(
        self, 
        owner_user_id: str, 
        user_name: str, 
        code: str, 
        channel: str,
        user_id: str
    ) -> Optional[str]:
        """Send approval DM to owner with inline buttons."""
        if not self._client:
            return None
        
        try:
            import discord
            
            components = PairingUIBuilder.create_discord_components(
                user_name=user_name,
                code=code,
                channel=channel,
                user_id=user_id
            )
            
            # Create view with buttons
            view = discord.ui.View()
            
            # Create buttons from components
            for row in components:
                for comp in row["components"]:
                    button = discord.ui.Button(
                        style=discord.ButtonStyle.success if comp["style"] == 3 else discord.ButtonStyle.danger,
                        label=comp["label"],
                        custom_id=comp["custom_id"]
                    )
                    
                    # Add callback
                    async def button_callback(interaction, custom_id=comp["custom_id"]):
                        await self._handle_pairing_interaction(interaction, custom_id)
                    
                    button.callback = button_callback
                    view.add_item(button)
            
            user = await self._client.fetch_user(int(owner_user_id))
            message = await user.send(
                content=f"**{user_name}** wants to chat. Approve access?",
                view=view
            )
            
            return str(message.id)
            
        except Exception as e:
            logger.error(f"Failed to send approval DM: {e}")
            return None
    
    async def reply(self, chat_id: str, text: str) -> None:
        """Reply to a chat/DM with a text message."""
        if not self._client:
            return
        
        try:
            if chat_id.isdigit():
                # Try channel first, then user, then fetch channel
                channel = self._client.get_channel(int(chat_id))
                if channel:
                    await channel.send(text)
                    return
                
                try:
                    user = await self._client.fetch_user(int(chat_id))
                    await user.send(text)
                    return
                except Exception:
                    # Last resort: fetch channel
                    channel = await self._client.fetch_channel(int(chat_id))
                    await channel.send(text)
            else:
                logger.error(f"Invalid chat_id format: {chat_id}")
        except Exception as e:
            logger.error(f"Failed to send reply: {e}")
    
    def _register_interactive_handlers(self):
        """Register handlers for interactive callbacks."""
        registry = self._interactive_registry
        
        # Register handler for command callbacks
        async def handle_command_callback(ctx):
            """Handle command callbacks from buttons."""
            payload = ctx.platform_data.get("decoded_payload", {})
            command = payload.get("command", "")
            
            # Get the Discord interaction object
            interaction = ctx.platform_data.get("interaction")
            if not interaction:
                return None
            
            # Parse the command (remove leading slash if present)
            if command.startswith("/"):
                command = command[1:]
            
            # Split command and args
            parts = command.split(maxsplit=1)
            cmd_name = parts[0] if parts else ""
            cmd_args = parts[1] if len(parts) > 1 else ""
            
            # Check if command exists in handlers
            if cmd_name in self._command_handlers:
                handler = self._command_handlers[cmd_name]
                try:
                    # Create a minimal message object for the handler
                    from praisonaiagents.bots import BotMessage, BotUser, BotChannel
                    message = BotMessage(
                        message_id=str(interaction.message.id) if interaction.message else "",
                        content=f"/{command}",
                        sender=BotUser(user_id=ctx.user_id),
                        channel=BotChannel(
                            channel_id=str(interaction.channel_id) if hasattr(interaction, "channel_id") else ""
                        ),
                        metadata={
                            "command": cmd_name,
                            "command_args": cmd_args
                        }
                    )
                    
                    if asyncio.iscoroutinefunction(handler):
                        await handler(message)
                    else:
                        handler(message)
                    
                    # Update the message to show command was executed
                    await interaction.edit_original_response(
                        content=f"{interaction.message.content}\n\n✅ Command executed: /{cmd_name}",
                        view=None
                    )
                    return f"Command {cmd_name} executed"
                except Exception as e:
                    logger.error(f"Command handler error: {e}")
                    await interaction.edit_original_response(
                        content=f"{interaction.message.content}\n\n❌ Error executing command",
                        view=None
                    )
                    return f"Error: {e}"
            
            logger.debug(f"Unknown command from button: {cmd_name}")
            return None
        
        # Register the command handler
        registry.register("command", handle_command_callback)
        
        # Register handler for pairing callbacks using the new system
        async def handle_pairing_callback(ctx):
            """Handle pairing callbacks through the new registry."""
            interaction = ctx.platform_data.get("interaction")
            if not interaction:
                return None
            
            # The pairing handler already exists, we just wrap it
            result = await self._pairing_callback_handler.handle_approval_callback(
                callback_data=ctx.callback_data,
                owner_user_id=ctx.user_id,
                bot_adapter=self
            )
            
            # Update the message with result
            if interaction.message:
                await interaction.edit_original_response(
                    content=f"{interaction.message.content}\n\n{result.message}",
                    view=None  # Remove buttons
                )
            
            return f"Pairing {result.action}"
        
        # Register the pairing handler
        registry.register("pair", handle_pairing_callback)
    
    async def _handle_pairing_interaction(self, interaction, custom_id: str):
        """Handle button interaction through the interactive registry."""
        try:
            # Defer the interaction
            await interaction.response.defer()
            
            # Create interactive context
            from praisonaiagents.bots import InteractiveContext
            ctx = InteractiveContext(
                callback_data=custom_id,
                user_id=str(interaction.user.id),
                message_id=str(interaction.message.id) if interaction.message else None,
                chat_id=str(interaction.channel_id) if hasattr(interaction, "channel_id") else None,
                bot_adapter=self,
                platform_data={
                    "interaction": interaction,
                }
            )
            
            # Try to dispatch through the interactive registry
            handled = await self._interactive_registry.dispatch(ctx)
            
            if not handled:
                # Fallback: handle legacy pairing callbacks
                if custom_id.startswith("pair:"):
                    result = await self._pairing_callback_handler.handle_approval_callback(
                        callback_data=custom_id,
                        owner_user_id=str(interaction.user.id),
                        bot_adapter=self
                    )
                    
                    # Edit the message with result
                    await interaction.edit_original_response(
                        content=f"{interaction.message.content}\n\n{result.message}",
                        view=None  # Remove buttons
                    )
                else:
                    logger.debug(f"Unhandled callback: {custom_id}")
            
        except Exception as e:
            logger.error(f"Failed to handle pairing interaction: {e}")
