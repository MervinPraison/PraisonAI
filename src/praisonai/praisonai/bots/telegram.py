"""
Telegram Bot implementation for PraisonAI.

Provides a full Telegram bot runtime with webhook/polling support,
command handling, and agent integration.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from praisonaiagents import Agent
    from praisonaiagents.bots.presentation import (
        MessagePresentation,
        PresentationLimits,
    )

from praisonai.bots._protocol_mixin import ChatCommandMixin, MessageHookMixin
from praisonaiagents.bots import (
    BotConfig,
    BotMessage,
    BotUser,
    BotChannel,
    MessageType,
    PlatformCapabilities,
)

from .media import split_media_from_output, is_audio_file
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
    get_command_registry
)
from ._session import BotSessionManager
from ._debounce import InboundDebouncer
from ._ack import AckReactor
from ._unknown_user import UnknownUserHandler, BotContext
from ._pairing_ui import PairingUIBuilder, PairingCallbackHandler
from ._streaming import StreamingConfig, StreamingMode, DraftStreamer
from ._rate_limit import RateLimiter
from ._resilience import deliver_with_retry, BackoffPolicy, TELEGRAM_BACKOFF
from ._dlq import OutboundDLQ
from ..gateway.unicode_utils import safe_error_message, safe_log_message, extract_root_cause_from_error
from ..gateway.pairing import PairingStore

logger = logging.getLogger(__name__)


class TelegramBot(ChatCommandMixin, MessageHookMixin):
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
        **kwargs,
    ):
        """Initialize the Telegram bot.
        
        Args:
            token: Telegram bot token from @BotFather
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
        
        # Initialize command access policy
        self._init_command_access_policy()
        
        # Initialize streaming config based on BotConfig
        if self.config.streaming:
            self._streaming_config = StreamingConfig(
                mode=StreamingMode.DRAFT,
                min_interval=self.config.stream_edit_interval_ms / 1000.0,  # Convert ms to seconds
                min_delta=50,  # Reasonable default for character delta
            )
        else:
            self._streaming_config = None
        self._rate_limiter = RateLimiter.for_platform("telegram")
        
        self._is_running = False
        self._bot_user: Optional[BotUser] = None
        self._application = None
        
        self._message_handlers: List[Callable] = []
        self._command_handlers: Dict[str, Callable] = {}
        self._started_at: Optional[float] = None
        
        # Create run control if busy mode is configured
        run_control = None
        if hasattr(self.config, 'busy_mode') and self.config.busy_mode != "queue":
            try:
                from ._run_control import SessionRunControl
                run_control = SessionRunControl(
                    busy_mode=self.config.busy_mode,
                    busy_ack_template=getattr(self.config, 'busy_ack', "⏳ {action} — will be considered next")
                )
            except ImportError:
                logger.warning("Run control not available, falling back to basic session management")
        
        # Use helper to build session manager
        from ._session import build_session_manager
        self._session: BotSessionManager = build_session_manager(
            self.config, 
            platform="telegram",
            run_control=run_control
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
        
        # Audio capabilities (set by BotCapabilities)
        self._stt_enabled: bool = False
        self._auto_tts: bool = False
        
        # Resilience
        self._monitor = None  # Lazy: ConnectionMonitor
        self._stop_event: Optional[asyncio.Event] = None
        
        # Outbound resilience configuration
        outbound_resilience = getattr(self.config, 'outbound_resilience', None)
        if outbound_resilience and getattr(outbound_resilience, 'enabled', True):
            # Use configured values
            self._outbound_backoff: BackoffPolicy = BackoffPolicy(
                initial_ms=getattr(outbound_resilience, 'initial_ms', 1000),
                max_ms=getattr(outbound_resilience, 'max_ms', 10000),
                factor=getattr(outbound_resilience, 'factor', 1.5),
                max_attempts=getattr(outbound_resilience, 'max_attempts', 3),
                jitter=getattr(outbound_resilience, 'jitter', 0.25)
            )
            # Initialize outbound DLQ if path is configured
            outbound_dlq_path = getattr(outbound_resilience, 'dlq_path', None)
            self._outbound_dlq: Optional[OutboundDLQ] = None
            if outbound_dlq_path:
                try:
                    self._outbound_dlq = OutboundDLQ(path=outbound_dlq_path)
                    logger.info(f"Outbound DLQ initialized at {outbound_dlq_path}")
                except Exception as e:
                    logger.warning(f"Failed to initialize outbound DLQ: {e}")
        else:
            # Default resilience settings
            self._outbound_backoff = BackoffPolicy(initial_ms=1000, max_ms=10000, factor=1.5, max_attempts=3)
            self._outbound_dlq = None
    
    
    def configure_streaming(self, config: StreamingConfig) -> None:
        """Configure streaming reply mode.
        
        Args:
            config: Streaming configuration. Set mode=StreamingMode.OFF to disable.
        """
        self._streaming_config = config
        logger.debug("TelegramBot: streaming configured, mode=%s", config.mode)
    
    def enable_stt(self, enabled: bool = True) -> None:
        """Enable STT for voice message transcription."""
        self._stt_enabled = enabled
    
    def enable_auto_tts(self, enabled: bool = True) -> None:
        """Enable auto-TTS for responses."""
        self._auto_tts = enabled
    
    def _init_command_access_policy(self):
        """Initialize command access policy from config.

        Uses the shared :func:`build_command_access_policy` builder so every
        adapter (Telegram, Slack, Discord) parses ``admin_users`` /
        ``user_allowed_commands`` identically and can't silently diverge.
        """
        self._command_policy = build_command_access_policy(self.config)

        # Get the global command registry
        self._command_registry = get_command_registry()
    
    def _register_interactive_handlers(self):
        """Register handlers for interactive callbacks."""
        registry = self._interactive_registry
        
        # Register handler for command callbacks
        async def handle_command_callback(ctx):
            """Handle command callbacks from buttons."""
            payload = ctx.platform_data.get("decoded_payload", {})
            command = payload.get("command", "")
            
            # Get the Telegram query object
            query = ctx.platform_data.get("query")
            if not query:
                return None
            
            # Parse the command (remove leading slash if present)
            if command.startswith("/"):
                command = command[1:]
            
            # Split command and args
            parts = command.split(maxsplit=1)
            cmd_name = parts[0] if parts else ""
            cmd_args = parts[1] if len(parts) > 1 else ""
            
            # Check permissions
            if not self._command_policy.can_run(ctx.user_id, cmd_name):
                await query.edit_message_text(
                    text=f"{query.message.text}\n\n⛔ You are not permitted to run /{cmd_name}",
                    parse_mode="Markdown"
                )
                return "Permission denied"
            
            # Check if command exists in handlers
            if cmd_name in self._command_handlers:
                handler = self._command_handlers[cmd_name]
                try:
                    # Create a minimal message object for the handler
                    from praisonaiagents.bots import BotMessage, BotUser, BotChannel
                    message = BotMessage(
                        message_id=ctx.message_id or "",
                        content=f"/{command}",
                        sender=BotUser(user_id=ctx.user_id),
                        channel=BotChannel(channel_id=ctx.chat_id or ""),
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
                    await query.edit_message_text(
                        text=f"{query.message.text}\n\n✅ Command executed: /{cmd_name}",
                        parse_mode="Markdown"
                    )
                    return f"Command {cmd_name} executed"
                except Exception as e:
                    logger.error(f"Command handler error: {e}")
                    await query.edit_message_text(
                        text=f"{query.message.text}\n\n❌ Error executing command",
                        parse_mode="Markdown"
                    )
                    return f"Error: {e}"
            
            logger.debug(f"Unknown command from button: {cmd_name}")
            return None
        
        # Register the command handler
        registry.register("command", handle_command_callback)
        
        # Register handler for pairing callbacks using the new system
        async def handle_pairing_callback(ctx):
            """Handle pairing callbacks through the new registry."""
            # The pairing handler already exists, we just wrap it
            result = await self._pairing_callback_handler.handle_approval_callback(
                callback_data=ctx.callback_data,
                owner_user_id=ctx.user_id,
                bot_adapter=self
            )
            
            # Update the message with result
            query = ctx.platform_data.get("query")
            if query and query.message:
                await query.edit_message_text(
                    text=f"{query.message.text}\n\n{result.message}",
                    parse_mode="Markdown"
                )
            
            return f"Pairing {result.action}"
        
        # Register the pairing handler
        registry.register("pair", handle_pairing_callback)
    
    @property
    def is_running(self) -> bool:
        return self._is_running
    
    @property
    def platform(self) -> str:
        return "telegram"
    
    @property
    def bot_user(self) -> Optional[BotUser]:
        return self._bot_user
    
    @property
    def capabilities(self) -> Dict[str, Any]:
        """Telegram supports all features."""
        return {
            "live_edit": True,
            "reactions": True,
            "typing": True,
            "text_limit": 4096,
            "edit_rate_limit": 1.0,
            "reaction_rate_limit": 0.5,
        }
    
    @property
    def platform_capabilities(self) -> PlatformCapabilities:
        """Return Telegram platform capabilities."""
        return self.default_capabilities()
    
    @classmethod
    def default_capabilities(cls) -> PlatformCapabilities:
        """Default Telegram platform capabilities."""
        return PlatformCapabilities(
            max_message_length=4096,
            length_unit="utf16",  # Telegram uses UTF-16 for length calculation
            supports_edit=True,  # Telegram supports message editing
            supports_typing=True,
            markdown_dialect="telegram_markdown_v2",
            needs_rate_limit=True,
            edit_interval_ms=1000,  # Telegram rate limits edits
            max_files_per_message=1,
            max_file_size_mb=50,  # Telegram supports up to 50MB for bots
            supported_file_types=["image/*", "audio/*", "video/*", "application/*"],
        )
    
    async def start(self) -> None:
        """Start the Telegram bot."""
        if self._is_running:
            logger.warning("Bot already running")
            return
        
        try:
            from telegram import Update, InlineKeyboardMarkup
            from telegram.ext import (
                Application,
                CommandHandler,
                MessageHandler,
                CallbackQueryHandler,
                filters,
                ContextTypes,
            )
        except ImportError:
            raise ImportError(
                "TelegramBot requires python-telegram-bot. "
                "Install with: pip install python-telegram-bot"
            )
        
        self._application = Application.builder().token(self._token).build()
        self._started_at = time.time()
        
        # Initialize bot context for pairing system
        self._bot_context = BotContext(
            config=self.config,
            pairing_store=self._pairing_store,
            adapter=self
        )
        
        bot_info = await self._application.bot.get_me()
        self._bot_user = BotUser(
            user_id=str(bot_info.id),
            username=bot_info.username,
            display_name=bot_info.first_name,
            is_bot=True,
        )
        
        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            # Use shared security pipeline for consistent enforcement
            message = await process_inbound_telegram_message(update, self)
            if not message:
                return  # Message was dropped by security checks
            
            for handler in self._message_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(message)
                    else:
                        handler(message)
                except Exception as e:
                    logger.error(f"Message handler error: {e}")
            
            if self._agent and not message.is_command:
                # Ack reaction
                ack_ctx = None
                if self._ack.enabled:
                    async def _tg_react(emoji, **kw):
                        try:
                            from telegram import ReactionTypeEmoji
                            await self._application.bot.set_message_reaction(
                                chat_id=update.message.chat_id,
                                message_id=update.message.message_id,
                                reaction=[ReactionTypeEmoji(emoji=emoji)],
                            )
                        except Exception:
                            pass  # Reactions may not be supported in all chats
                    async def _tg_unreact(emoji, **kw):
                        try:
                            await self._application.bot.set_message_reaction(
                                chat_id=update.message.chat_id,
                                message_id=update.message.message_id,
                                reaction=[],
                            )
                        except Exception:
                            pass
                    ack_ctx = await self._ack.ack(react_fn=_tg_react)
                
                user_id = str(update.message.from_user.id) if update.message.from_user else "unknown"
                user_name = (
                    update.message.from_user.username or update.message.from_user.first_name or ""
                ) if update.message.from_user else ""
                # Download/validate any inbound photo or document so the agent's
                # vision capability can act on it (Issue #2350).
                attachments = await self._cache_inbound_telegram_media(update)
                try:
                    message_text = await self._debouncer.debounce(user_id, message.content)
                    
                    # Check if streaming is enabled and configured
                    streaming_enabled = (
                        self._streaming_config and 
                        self._streaming_config.mode != StreamingMode.OFF
                    )
                    
                    if streaming_enabled:
                        # Streaming path
                        streamer = DraftStreamer(
                            adapter=self,
                            channel_id=str(update.message.chat_id),
                            config=self._streaming_config,
                            rate_limiter=self._rate_limiter,
                            platform="telegram",
                        )
                        
                        # Start streaming (send placeholder)
                        placeholder_message_id = await streamer.start()
                        
                        try:
                            # Get response with streaming callback - include message_id and account for durability
                            response = await self._session.chat(
                                self._agent, user_id, message_text,
                                chat_id=str(update.message.chat_id) if update.message.chat_id else "",
                                user_name=user_name,
                                message_id=str(update.message.message_id),
                                account=getattr(self.config, "account", "default"),
                                stream_callback=streamer.on_event,
                                attachments=attachments or None,
                            )

                            # Consume the agent-attached portable presentation
                            # now (the session-contract clearing step for this
                            # turn) so a later cancel/return doesn't leave stale
                            # buttons for the next turn. Rendered after the text.
                            presentation = self._session.pop_last_presentation(user_id)

                            # Apply message hooks to final response (same as non-streaming path)
                            send_result = self.fire_message_sending(
                                str(update.message.chat_id), str(response),
                                reply_to=str(update.message.message_id),
                            )
                            if send_result["cancel"]:
                                # Cancel: delete the placeholder message
                                try:
                                    await self.delete_message(
                                        str(update.message.chat_id), placeholder_message_id
                                    )
                                except Exception:
                                    pass  # Ignore deletion errors
                                return
                            
                            # Handle media content before finalizing (extract MEDIA: markers)
                            from .media import split_media_from_output
                            parsed = split_media_from_output(send_result["content"])
                            text_content = parsed["text"]
                            media_urls = parsed.get("media_urls", [])
                            
                            # Finalize with text content (after hook processing and media extraction)
                            await streamer.finalize(text_content if text_content else send_result["content"])
                            
                            # Send media files separately (same as non-streaming path)
                            if media_urls:
                                for media_path in media_urls:
                                    if os.path.exists(media_path):
                                        try:
                                            from .media import is_audio_file
                                            if is_audio_file(media_path):
                                                with open(media_path, "rb") as f:
                                                    if parsed.get("audio_as_voice", False):
                                                        await self._application.bot.send_voice(
                                                            chat_id=update.message.chat_id, voice=f
                                                        )
                                                    else:
                                                        await self._application.bot.send_audio(
                                                            chat_id=update.message.chat_id, audio=f
                                                        )
                                        except Exception as e:
                                            logger.error(f"Failed to send media: {e}")
                            
                            # Render the agent-attached portable presentation
                            # (buttons/menus) natively after the streamed text.
                            # ``presentation`` was popped right after chat() above.
                            try:
                                if presentation is not None:
                                    await self.render_presentation(
                                        str(update.message.chat_id), presentation
                                    )
                            except Exception as e:  # pragma: no cover — defensive
                                logger.debug("presentation render skipped: %s", e)

                            # Fire sent hooks
                            self.fire_message_sent(
                                str(update.message.chat_id), send_result["content"],
                            )
                            
                        except Exception as agent_error:
                            # Agent failed: clean up placeholder message
                            try:
                                await self.delete_message(
                                    str(update.message.chat_id), placeholder_message_id
                                )
                            except Exception:
                                pass  # Ignore deletion errors
                            # Re-raise the original error to be handled below
                            raise agent_error
                        
                    else:
                        # Legacy non-streaming path
                        # Show typing indicator with renewal during long operation
                        if self.config.typing_indicator:
                            from ._typing_indicator import with_typing_renewal
                            
                            async def _typing_action():
                                await update.message.chat.send_action("typing")
                            
                            response = await with_typing_renewal(
                                typing_func=_typing_action,
                                operation_coro=self._session.chat(
                                    self._agent, user_id, message_text,
                                    chat_id=str(update.message.chat_id) if update.message.chat_id else "",
                                    user_name=user_name,
                                    message_id=str(update.message.message_id),
                                    account=getattr(self.config, "account", "default"),
                                    attachments=attachments or None,
                                )
                            )
                        else:
                            response = await self._session.chat(
                                self._agent, user_id, message_text,
                                chat_id=str(update.message.chat_id) if update.message.chat_id else "",
                                user_name=user_name,
                                message_id=str(update.message.message_id),
                                account=getattr(self.config, "account", "default"),
                                attachments=attachments or None,
                            )

                        # Consume the agent-attached portable presentation now
                        # (session-contract clearing step) so a cancel/return
                        # below doesn't leave stale buttons for the next turn.
                        presentation = self._session.pop_last_presentation(user_id)

                        # Normal send flow for non-streaming
                        send_result = self.fire_message_sending(
                            str(update.message.chat_id), str(response),
                            reply_to=str(update.message.message_id),
                        )
                        if send_result["cancel"]:
                            return
                        await self._send_response_with_media(
                            update.message.chat_id,
                            send_result["content"],
                            reply_to=update.message.message_id,
                        )
                        # If the agent attached a portable presentation
                        # (buttons/menus), render it natively as an inline
                        # keyboard. The text reply above already serves as the
                        # plain-text fallback, so a render failure degrades
                        # gracefully rather than dropping the reply.
                        # ``presentation`` was popped right after chat() above.
                        try:
                            if presentation is not None:
                                await self.render_presentation(
                                    str(update.message.chat_id), presentation
                                )
                        except Exception as e:  # pragma: no cover — defensive
                            logger.debug("presentation render skipped: %s", e)
                        self.fire_message_sent(
                            str(update.message.chat_id), send_result["content"],
                        )
                    # Done reaction
                    if ack_ctx:
                        await self._ack.done(ack_ctx, react_fn=_tg_react, unreact_fn=_tg_unreact)
                except Exception as e:
                    logger.error(f"Agent error: {safe_log_message(e)}")
                    user_error = extract_root_cause_from_error(str(e))
                    await update.message.reply_text(f"Error: {safe_error_message(user_error)}")
                finally:
                    # Inbound media is cached to temp files for this turn only;
                    # remove them so media-heavy bots don't fill the temp volume.
                    for _path in attachments:
                        try:
                            os.remove(_path)
                        except OSError:
                            pass
        
        async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """Handle voice messages."""
            await handle_message(update, context)
        
        async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message or not update.message.text:
                return

            message = await process_inbound_telegram_message(update, self)
            if not message:
                return

            command = message.command
            user_id = message.sender.user_id if message.sender else "unknown"
            
            if command:
                # Check command permissions
                if not self._command_policy.can_run(user_id, command):
                    await update.message.reply_text(f"⛔ You are not permitted to run /{command}")
                    return
                
                # Handle custom registered commands
                if command in self._command_handlers:
                    handler = self._command_handlers[command]
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(message)
                        else:
                            handler(message)
                    except Exception as e:
                        logger.error(f"Command handler error: {e}")
        
        async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message:
                return
            message = await process_inbound_telegram_message(update, self)
            if not message:
                return
            user_id = message.sender.user_id if message.sender else "unknown"
            # Check command permissions
            if not self._command_policy.can_run(user_id, "status"):
                await update.message.reply_text("⛔ You are not permitted to run /status")
                return
            await update.message.reply_text(self._format_status())
        
        async def handle_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message:
                return
            message = await process_inbound_telegram_message(update, self)
            if not message:
                return
            user_id = message.sender.user_id if message.sender else "unknown"
            # Check command permissions
            if not self._command_policy.can_run(user_id, "new"):
                await update.message.reply_text("⛔ You are not permitted to run /new")
                return
            # Pass the chat route so a /new in a group/channel clears the
            # shared per_chat session (Issue #2376); a no-op for per_user.
            self._session.reset(
                user_id,
                account=getattr(self.config, "account", "default"),
                chat_id=str(update.message.chat_id) if update.message.chat_id else "",
            )
            await update.message.reply_text("Session reset. Starting fresh conversation.")
        
        async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message:
                return
            message = await process_inbound_telegram_message(update, self)
            if not message:
                return
            user_id = message.sender.user_id if message.sender else "unknown"
            # Help is always allowed (in ALWAYS_ALLOWED set)
            # Use instance method to include custom commands
            help_text = self._format_help_with_permissions(user_id)
            await update.message.reply_text(help_text)
        
        async def handle_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message:
                return
            message = await process_inbound_telegram_message(update, self)
            if not message:
                return
            user_id = message.sender.user_id if message.sender else "unknown"
            # Check command permissions
            if not self._command_policy.can_run(user_id, "stop"):
                await update.message.reply_text("⛔ You are not permitted to run /stop")
                return
            response = handle_stop_command(self._session, user_id)
            await update.message.reply_text(response)
        
        async def handle_whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message:
                return
            message = await process_inbound_telegram_message(update, self)
            if not message:
                return
            user_id = message.sender.user_id if message.sender else "unknown"
            username = message.sender.username if message.sender else None
            # Whoami is always allowed (in ALWAYS_ALLOWED set)
            response = self._command_registry.format_whoami(user_id, username, self._command_policy)
            await update.message.reply_text(response)
        
        async def handle_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message or not update.message.text:
                return
            message = await process_inbound_telegram_message(update, self)
            if not message:
                return
            user_id = message.sender.user_id if message.sender else "unknown"
            # Check command permissions
            if not self._command_policy.can_run(user_id, "model"):
                await update.message.reply_text("⛔ You are not permitted to run /model")
                return
            # Extract model name from command
            parts = update.message.text.split(maxsplit=1)
            model_name = parts[1] if len(parts) > 1 else None
            response = handle_model_command(self._session, user_id, model_name, self._agent)
            await update.message.reply_text(response)
        
        async def handle_usage(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message:
                return
            message = await process_inbound_telegram_message(update, self)
            if not message:
                return
            user_id = message.sender.user_id if message.sender else "unknown"
            # Check command permissions
            if not self._command_policy.can_run(user_id, "usage"):
                await update.message.reply_text("⛔ You are not permitted to run /usage")
                return
            response = handle_usage_command(self._session, user_id, self._agent)
            await update.message.reply_text(response)
        
        async def handle_compress(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message:
                return
            message = await process_inbound_telegram_message(update, self)
            if not message:
                return
            user_id = message.sender.user_id if message.sender else "unknown"
            # Check command permissions
            if not self._command_policy.can_run(user_id, "compress"):
                await update.message.reply_text("⛔ You are not permitted to run /compress")
                return
            response = handle_compress_command(self._session, user_id, self._agent)
            await update.message.reply_text(response)
        
        async def handle_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message or not update.message.text:
                return
            message = await process_inbound_telegram_message(update, self)
            if not message:
                return
            user_id = message.sender.user_id if message.sender else "unknown"
            # Check command permissions
            if not self._command_policy.can_run(user_id, "queue"):
                await update.message.reply_text("⛔ You are not permitted to run /queue")
                return
            # Extract message text from command
            parts = update.message.text.split(maxsplit=1)
            message_text = parts[1] if len(parts) > 1 else None
            response = handle_queue_command(self._session, user_id, message_text)
            await update.message.reply_text(response)

        async def handle_learn(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message or not update.message.text:
                return
            message = await process_inbound_telegram_message(update, self)
            if not message:
                return
            user_id = message.sender.user_id if message.sender else "unknown"
            if not self._command_policy.can_run(user_id, "learn"):
                await update.message.reply_text("⛔ You are not permitted to run /learn")
                return
            parts = update.message.text.split(maxsplit=1)
            request = parts[1] if len(parts) > 1 else None
            response = handle_learn_command(self._agent, request)
            await update.message.reply_text(response)

        async def handle_undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message:
                return
            message = await process_inbound_telegram_message(update, self)
            if not message:
                return
            user_id = message.sender.user_id if message.sender else "unknown"
            if not self._command_policy.can_run(user_id, "undo"):
                await update.message.reply_text("⛔ You are not permitted to run /undo")
                return
            response = handle_undo_command(self._agent)
            await update.message.reply_text(response)

        async def handle_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message:
                return
            message = await process_inbound_telegram_message(update, self)
            if not message:
                return
            user_id = message.sender.user_id if message.sender else "unknown"
            if not self._command_policy.can_run(user_id, "sessions"):
                await update.message.reply_text("⛔ You are not permitted to run /sessions")
                return
            response = handle_sessions_command(self._session, user_id)
            await update.message.reply_text(response)

        async def handle_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message or not update.message.text:
                return
            message = await process_inbound_telegram_message(update, self)
            if not message:
                return
            user_id = message.sender.user_id if message.sender else "unknown"
            if not self._command_policy.can_run(user_id, "resume"):
                await update.message.reply_text("⛔ You are not permitted to run /resume")
                return
            parts = update.message.text.split(maxsplit=1)
            session_id = parts[1] if len(parts) > 1 else None
            response = handle_resume_command(self._session, user_id, session_id)
            await update.message.reply_text(response)

        async def handle_retry(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message:
                return
            message = await process_inbound_telegram_message(update, self)
            if not message:
                return
            user_id = message.sender.user_id if message.sender else "unknown"
            if not self._command_policy.can_run(user_id, "retry"):
                await update.message.reply_text("⛔ You are not permitted to run /retry")
                return
            last_user_msg = get_last_user_message(self._session, user_id)
            if not last_user_msg:
                await update.message.reply_text(
                    "ℹ️ Nothing to retry — no previous message found."
                )
                return
            user_name = (
                update.message.from_user.username or update.message.from_user.first_name or ""
            ) if update.message.from_user else ""
            await update.message.reply_text("🔁 Retrying your last message…")
            try:
                response = await self._session.chat(
                    self._agent, user_id, last_user_msg,
                    chat_id=str(update.message.chat_id) if update.message.chat_id else "",
                    user_name=user_name,
                    message_id=str(update.message.message_id),
                    account=getattr(self.config, "account", "default"),
                )
                await update.message.reply_text(response)
            except Exception as e:  # noqa: BLE001 - surface a friendly message
                logger.warning("retry failed: %s", e)
                await update.message.reply_text(f"❌ Retry failed: {e}")

        async def handle_reasoning(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.message:
                return
            message = await process_inbound_telegram_message(update, self)
            if not message:
                return
            user_id = message.sender.user_id if message.sender else "unknown"
            if not self._command_policy.can_run(user_id, "reasoning"):
                await update.message.reply_text("⛔ You are not permitted to run /reasoning")
                return
            response = handle_reasoning_command(self._session, user_id, self._agent)
            await update.message.reply_text(response)

        self._application.add_handler(CommandHandler("status", handle_status))
        self._application.add_handler(CommandHandler("new", handle_new))
        self._application.add_handler(CommandHandler("help", handle_help))
        self._application.add_handler(CommandHandler("stop", handle_stop))
        self._application.add_handler(CommandHandler("whoami", handle_whoami))
        self._application.add_handler(CommandHandler("model", handle_model))
        self._application.add_handler(CommandHandler("usage", handle_usage))
        self._application.add_handler(CommandHandler("compress", handle_compress))
        self._application.add_handler(CommandHandler("queue", handle_queue))
        self._application.add_handler(CommandHandler("learn", handle_learn))
        self._application.add_handler(CommandHandler("undo", handle_undo))
        self._application.add_handler(CommandHandler("sessions", handle_sessions))
        self._application.add_handler(CommandHandler("resume", handle_resume))
        self._application.add_handler(CommandHandler("retry", handle_retry))
        self._application.add_handler(CommandHandler("reasoning", handle_reasoning))
        
        for command in self._command_handlers:
            self._application.add_handler(CommandHandler(command, handle_command))
        
        self._application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
        )
        
        # Add callback query handler for all interactive buttons
        async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
            query = update.callback_query
            if not query or not query.data:
                return
            
            # Answer the callback query to stop loading spinner
            await query.answer()
            
            # Create interactive context
            from praisonaiagents.bots import InteractiveContext
            ctx = InteractiveContext(
                callback_data=query.data,
                user_id=str(query.from_user.id),
                message_id=str(query.message.message_id) if query.message else None,
                chat_id=str(query.message.chat_id) if query.message else None,
                bot_adapter=self,
                platform_data={
                    "update": update,
                    "context": context,
                    "query": query
                }
            )
            
            # Try to dispatch through the interactive registry
            handled = await self._interactive_registry.dispatch(ctx)
            
            if not handled:
                # Fallback: handle legacy pairing callbacks
                if query.data.startswith("pair:"):
                    result = await self._pairing_callback_handler.handle_approval_callback(
                        callback_data=query.data,
                        owner_user_id=str(query.from_user.id),
                        bot_adapter=self
                    )
                    
                    # Update the message with result
                    await query.edit_message_text(
                        text=f"{query.message.text}\n\n{result.message}",
                        parse_mode="Markdown"
                    )
                else:
                    logger.debug(f"Unhandled callback: {query.data}")
        
        self._application.add_handler(CallbackQueryHandler(handle_callback_query))
        
        # Add voice/audio handlers
        self._application.add_handler(
            MessageHandler(filters.VOICE | filters.AUDIO, handle_voice)
        )

        # Add photo/document handlers (Issue #2350): route inbound media to the
        # agent's vision capability via the same message pipeline.
        self._application.add_handler(
            MessageHandler(
                (filters.PHOTO | filters.VIDEO | filters.Document.ALL) & ~filters.COMMAND,
                handle_message,
            )
        )
        
        self._is_running = True
        logger.info(f"Telegram bot started: @{self._bot_user.username}")
        
        # Initialize connection monitor for resilience
        from ._resilience import ConnectionMonitor, TELEGRAM_BACKOFF, is_recoverable_error, is_conflict_error, sleep_with_abort
        self._monitor = ConnectionMonitor(platform="telegram", policy=TELEGRAM_BACKOFF)
        
        if self.config.is_webhook_mode:
            await self._application.run_webhook(
                listen="0.0.0.0",
                port=8443,
                url_path=self.config.webhook_path,
                webhook_url=f"{self.config.webhook_url}{self.config.webhook_path}",
            )
        else:
            # Resilient polling loop with exponential backoff
            self._stop_event = asyncio.Event()
            while not self._stop_event.is_set():
                try:
                    await self._application.initialize()
                    await self._application.start()
                    await self._application.updater.start_polling(
                        poll_interval=self.config.polling_interval,
                    )
                    self._monitor.record_success()
                    
                    # Block until stop() is called
                    await self._stop_event.wait()
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    if is_conflict_error(e):
                        logger.error(
                            "[telegram] Another bot instance is running with this token. "
                            "Stop the other instance first."
                        )
                        break  # Don't retry conflicts
                    
                    if is_recoverable_error(e, "telegram") and self._monitor.should_retry():
                        delay = self._monitor.record_error(e)
                        completed = await sleep_with_abort(delay, self._stop_event)
                        if not completed:
                            break  # Abort signaled during sleep
                        # Attempt reconnect
                        try:
                            await self._application.updater.stop()
                            await self._application.stop()
                            await self._application.shutdown()
                        except Exception:
                            pass
                        # Rebuild application for clean reconnect
                        from telegram.ext import Application
                        self._application = Application.builder().token(self._token).build()
                        continue
                    else:
                        logger.error(f"[telegram] Unrecoverable error: {e}")
                        break
                finally:
                    try:
                        await self._application.updater.stop()
                        await self._application.stop()
                        await self._application.shutdown()
                    except Exception:
                        pass
                    self._is_running = False
    
    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if not self._is_running:
            return
        
        # Cancel pending debounce timers
        self._debouncer.cancel_all()
        
        # Signal the stop event so the start() loop exits cleanly
        if hasattr(self, '_stop_event') and self._stop_event:
            self._stop_event.set()
        else:
            # Fallback for webhook mode or direct stop
            self._is_running = False
            if self._application:
                try:
                    await self._application.stop()
                    await self._application.shutdown()
                except Exception as e:
                    logger.warning(f"Error during stop: {e}")
        
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
        
        # Use retry wrapper for reliable delivery
        send_kwargs = dict(kwargs)  # Copy to avoid closure issues
        sent = await deliver_with_retry(
            lambda: self._application.bot.send_message(**send_kwargs),
            policy=self._outbound_backoff,
            platform="telegram",
            parked_store=self._outbound_dlq,
            reply_data={
                "channel_id": channel_id,
                "reply_text": text,
                "thread_id": thread_id or "",
                "reply_to": reply_to or "",
            }
        )
        
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
        """Send a long message, splitting with markdown-aware chunking."""
        from ._chunk import chunk_message

        max_len = self.config.max_message_length

        if len(text) <= max_len:
            kwargs = {"chat_id": chat_id, "text": text}
            if reply_to:
                kwargs["reply_to_message_id"] = reply_to
            
            # Use retry wrapper for reliable delivery
            # Create a lambda that captures kwargs properly
            send_kwargs = dict(kwargs)  # Copy to avoid closure issues
            await deliver_with_retry(
                lambda: self._application.bot.send_message(**send_kwargs),
                policy=self._outbound_backoff,
                platform="telegram",
                parked_store=self._outbound_dlq,
                reply_data={
                    "channel_id": str(chat_id),
                    "reply_text": text,
                    "reply_to": str(reply_to) if reply_to else "",
                }
            )
        else:
            chunks = chunk_message(text, max_length=max_len, preserve_fences=True)
            for i, chunk in enumerate(chunks):
                kwargs = {"chat_id": chat_id, "text": chunk}
                if i == 0 and reply_to:
                    kwargs["reply_to_message_id"] = reply_to
                
                # Use retry wrapper for each chunk
                send_kwargs = dict(kwargs)  # Copy to avoid closure issues
                await deliver_with_retry(
                    lambda: self._application.bot.send_message(**send_kwargs),
                    policy=self._outbound_backoff,
                    platform="telegram",
                    parked_store=self._outbound_dlq,
                    reply_data={
                        "channel_id": str(chat_id),
                        "reply_text": chunk,
                        "reply_to": str(reply_to) if reply_to and i == 0 else "",
                    }
                )
    
    async def _cache_inbound_telegram_media(self, update) -> List[str]:
        """Download and validate inbound photo/document for the agent (Issue #2350).

        Returns a list of cached local file paths the agent's vision capability
        can act on. Empty when media handling is disabled or no media present.
        """
        try:
            from ._media import cache_inbound_media, resolve_max_inbound_media_bytes
        except Exception as e:  # pragma: no cover — defensive
            logger.warning("Inbound media helper unavailable: %s", e)
            return []

        # Core BotConfig has no media field; the operator's
        # max_inbound_media_bytes (including 0 to disable) is carried through
        # config.metadata. Defaults to the shared cap so inbound media is
        # enabled by default (Issue #2350).
        max_bytes = resolve_max_inbound_media_bytes(self.config)
        if not max_bytes or max_bytes <= 0:
            return []
        if not getattr(update, "message", None):
            return []

        paths: List[str] = []

        async def _fetch(file_obj, kind: str, filename: Optional[str] = None):
            try:
                tg_file = await file_obj.get_file()
                # Reject oversized files before buffering them in memory when
                # Telegram declares the size.
                file_size = getattr(tg_file, "file_size", None) or getattr(
                    file_obj, "file_size", None
                )
                if file_size and file_size > max_bytes:
                    logger.warning(
                        "Inbound %s exceeds %s bytes (declared %s); skipping",
                        kind, max_bytes, file_size,
                    )
                    return
                if file_size:
                    # Size is declared and within cap: in-memory download is safe.
                    data = bytes(await tg_file.download_as_bytearray())
                    path = cache_inbound_media(
                        data, kind=kind, max_bytes=max_bytes, filename=filename
                    )
                else:
                    # Unknown size: stream to disk first so the path-based cap
                    # (os.path.getsize) rejects oversized media before it is
                    # read into memory. Falls back to in-memory if the streaming
                    # download API is unavailable.
                    download_to_drive = getattr(tg_file, "download_to_drive", None)
                    if download_to_drive is not None:
                        tmp = tempfile.mkstemp(prefix="inbound_tg_")
                        os.close(tmp[0])
                        tmp_path = tmp[1]
                        try:
                            await download_to_drive(custom_path=tmp_path)
                            path = cache_inbound_media(
                                tmp_path, kind=kind, max_bytes=max_bytes,
                                filename=filename,
                            )
                        finally:
                            try:
                                os.remove(tmp_path)
                            except OSError:
                                pass
                    else:  # pragma: no cover — older PTB without download_to_drive
                        data = bytes(await tg_file.download_as_bytearray())
                        path = cache_inbound_media(
                            data, kind=kind, max_bytes=max_bytes, filename=filename
                        )
                paths.append(path)
            except Exception as e:
                logger.warning("Failed to cache inbound %s: %s", kind, e)

        # Photos arrive as a list of sizes; the last entry is the largest.
        if update.message.photo:
            await _fetch(update.message.photo[-1], "image")

        # Native videos (sent as a video, not a document attachment).
        video = getattr(update.message, "video", None)
        if video is not None:
            await _fetch(video, "video", filename=getattr(video, "file_name", None))

        doc = update.message.document
        if doc is not None:
            mime = (getattr(doc, "mime_type", "") or "").lower()
            if mime.startswith("image/"):
                kind = "image"
            elif mime.startswith("video/"):
                kind = "video"
            elif mime.startswith("audio/"):
                kind = "audio"
            else:
                kind = "document"
            await _fetch(doc, kind, filename=getattr(doc, "file_name", None))

        return paths

    async def _transcribe_audio(self, update) -> Optional[str]:
        """Download and transcribe voice/audio message."""
        if not self._stt_enabled:
            return None
        
        try:
            # Get file info
            if update.message.voice:
                file = await update.message.voice.get_file()
            elif update.message.audio:
                file = await update.message.audio.get_file()
            else:
                return None
            
            # Download to temp file
            temp_path = os.path.join(tempfile.gettempdir(), f"voice_{file.file_id}.ogg")
            await file.download_to_drive(temp_path)
            
            # Transcribe using existing stt_tool
            try:
                from praisonai.tools.audio import stt_tool
                result = stt_tool(temp_path)
                if result.get("success"):
                    text = result.get("text", "")
                    logger.info(f"Transcribed voice message: {text[:50]}...")
                    return f"[Voice message]: {text}"
                else:
                    logger.warning(f"STT failed: {result.get('error')}")
                    return None
            finally:
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    
        except Exception as e:
            logger.error(f"Audio transcription error: {e}")
            return None
    
    async def _send_response_with_media(
        self,
        chat_id: int,
        response: str,
        reply_to: Optional[int] = None,
    ) -> None:
        """Send response, extracting and sending any MEDIA: files."""
        # Parse response for media
        parsed = split_media_from_output(response)
        text = parsed["text"]
        media_urls = parsed.get("media_urls", [])
        audio_as_voice = parsed.get("audio_as_voice", False)
        
        # Send text first if present
        if text:
            await self._send_long_message(chat_id, text, reply_to=reply_to)
        
        # Send audio files
        for media_path in media_urls:
            if not os.path.exists(media_path):
                logger.warning(f"Media file not found: {media_path}")
                continue
            
            if is_audio_file(media_path):
                try:
                    with open(media_path, "rb") as f:
                        if audio_as_voice:
                            # Use retry wrapper for voice messages with proper seek
                            async def send_voice():
                                f.seek(0)  # Reset file position before each attempt
                                return await self._application.bot.send_voice(
                                    chat_id=chat_id, voice=f
                                )
                            await deliver_with_retry(
                                send_voice,
                                policy=self._outbound_backoff,
                                platform="telegram",
                                parked_store=None,  # Don't DLQ media for now (complex replay)
                            )
                        else:
                            # Use retry wrapper for audio messages with proper seek
                            async def send_audio():
                                f.seek(0)  # Reset file position before each attempt
                                return await self._application.bot.send_audio(
                                    chat_id=chat_id, audio=f
                                )
                            await deliver_with_retry(
                                send_audio,
                                policy=self._outbound_backoff,
                                platform="telegram",
                                parked_store=None,  # Don't DLQ media for now (complex replay)
                            )
                except Exception as e:
                    logger.error(f"Failed to send audio: {e}")

    
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
    
    async def add_reaction(self, channel_id: str, message_id: str, emoji: str) -> bool:
        """Add a reaction to a message."""
        if not self._application:
            return False
        
        try:
            from telegram import ReactionTypeEmoji
            await self._application.bot.set_message_reaction(
                chat_id=int(channel_id),
                message_id=int(message_id),
                reaction=[ReactionTypeEmoji(emoji=emoji)],
            )
            return True
        except Exception as e:
            logger.debug(f"Failed to add reaction: {e}")
            return False
    
    async def remove_reaction(self, channel_id: str, message_id: str, emoji: str) -> bool:
        """Remove a reaction from a message.
        
        Note: Telegram's setMessageReaction API is set-based - it replaces all bot reactions.
        To remove a specific emoji, we would need to fetch current reactions and filter out
        the target. Since there's no getMessageReactions API, we'll clear all bot reactions
        as a simpler approach (the bot typically has only one reaction anyway).
        """
        if not self._application:
            return False
        
        try:
            # Telegram API: send empty reaction list to remove all bot reactions
            # This is a known limitation - we can't selectively remove individual reactions
            await self._application.bot.set_message_reaction(
                chat_id=int(channel_id),
                message_id=int(message_id),
                reaction=[],
            )
            return True
        except Exception as e:
            logger.debug(f"Failed to remove reaction: {e}")
            return False
    
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
    
    async def probe(self):
        """Test Telegram API connectivity without starting the bot."""
        from praisonaiagents.bots import ProbeResult
        started = time.time()
        try:
            import aiohttp
            url = f"https://api.telegram.org/bot{self._token}/getMe"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    elapsed = (time.time() - started) * 1000
                    if resp.status == 200 and data.get("ok"):
                        result = data.get("result", {})
                        return ProbeResult(
                            ok=True,
                            platform="telegram",
                            elapsed_ms=elapsed,
                            bot_username=result.get("username"),
                            details={
                                "bot_id": result.get("id"),
                                "can_join_groups": result.get("can_join_groups"),
                                "can_read_all_group_messages": result.get("can_read_all_group_messages"),
                                "supports_inline_queries": result.get("supports_inline_queries"),
                            },
                        )
                    else:
                        return ProbeResult(
                            ok=False,
                            platform="telegram",
                            elapsed_ms=elapsed,
                            error=data.get("description", f"HTTP {resp.status}"),
                        )
        except Exception as e:
            elapsed = (time.time() - started) * 1000
            return ProbeResult(
                ok=False,
                platform="telegram",
                elapsed_ms=elapsed,
                error=str(e),
            )

    async def health(self):
        """Get detailed health status of the Telegram bot."""
        return await self._default_health()

    def _format_status(self) -> str:
        """Format /status response."""
        return format_status(self._agent, self.platform, self._started_at, self._is_running)
    
    def _format_help(self) -> str:
        """Format /help response."""
        extra = {cmd: "Custom command" for cmd in self._command_handlers}
        return format_help(self._agent, self.platform, extra)
    
    def _format_help_with_permissions(self, user_id: str) -> str:
        """Format /help response with permission filtering and custom commands."""
        # Get allowed commands for this user
        all_commands = self._command_registry.get_command_names() | set(self._command_handlers.keys())
        
        if self._command_policy:
            allowed = self._command_policy.get_allowed_commands(user_id, all_commands)
        else:
            allowed = all_commands
        
        agent_name = self._agent.name if self._agent else "No agent"
        model = getattr(self._agent, "llm", "default") if self._agent else "default"
        
        lines = ["Available Commands"]
        
        # Built-in commands from registry
        for cmd in sorted(allowed):
            if cmd in self._command_registry.get_all_commands():
                cmd_info = self._command_registry.get_command(cmd)
                desc = cmd_info.get("description", "No description")
                lines.append(f"/{cmd} - {desc}")
            elif cmd in self._command_handlers:
                # Custom commands
                lines.append(f"/{cmd} - Custom command")
        
        lines.append(f"\nAgent: {agent_name}")
        lines.append(f"Model: {model}")
        
        return "\n".join(lines)
    
    def _convert_update_to_message(self, update, override_text: Optional[str] = None) -> BotMessage:
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
        
        # Use override text for transcribed audio, otherwise message text
        content = override_text if override_text else (msg.text or "")
        msg_type = MessageType.COMMAND if content and content.startswith("/") else MessageType.TEXT
        
        return BotMessage(
            message_id=str(msg.message_id),
            content=content,
            message_type=msg_type,
            sender=sender,
            channel=channel,
            timestamp=msg.date.timestamp() if msg.date else 0,
            thread_id=str(msg.message_thread_id) if msg.message_thread_id else None,
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
        if not self._application:
            return None
        
        try:
            from telegram import InlineKeyboardMarkup
            
            keyboard = PairingUIBuilder.create_telegram_keyboard(
                user_name=user_name,
                code=code, 
                channel=channel,
                user_id=user_id
            )
            
            message = await self._application.bot.send_message(
                chat_id=owner_user_id,
                text=f"*{user_name}* wants to chat. Approve access?",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup.from_dict(keyboard)
            )
            
            return str(message.message_id)
            
        except Exception as e:
            logger.error(f"Failed to send approval DM: {e}")
            return None
    
    async def reply(self, chat_id: str, text: str) -> None:
        """Reply to a chat/DM with a text message."""
        if not self._application:
            return
        
        try:
            await self._application.bot.send_message(
                chat_id=chat_id,
                text=text
            )
        except Exception as e:
            logger.error(f"Failed to send reply: {e}")

    @property
    def presentation_limits(self) -> "PresentationLimits":
        """Telegram presentation limits (see ``SupportsPresentation``)."""
        from praisonaiagents.bots.presentation import PresentationLimits
        return PresentationLimits.telegram()

    def truncate_presentation(
        self, presentation: "MessagePresentation"
    ) -> "MessagePresentation":
        """Adapt a portable presentation to Telegram's limits."""
        from praisonaiagents.bots.presentation import adapt_presentation
        return adapt_presentation(presentation, self.presentation_limits)

    async def render_presentation(
        self,
        target: str,
        presentation: "MessagePresentation",
    ) -> Optional[str]:
        """Render a portable presentation as a Telegram inline keyboard.

        Implements ``SupportsPresentation``: delegates to
        ``TelegramPresentationRenderer`` (which runs ``adapt_presentation``
        internally), then sends the resulting text + ``reply_markup`` natively.
        Returns the sent message id, or ``None`` if delivery failed.
        """
        if not self._application:
            return None
        try:
            from telegram import (
                InlineKeyboardButton,
                InlineKeyboardMarkup,
                WebAppInfo,
            )
            from ._presentation_renderer import TelegramPresentationRenderer

            def _build_button(btn: Dict[str, Any]) -> "InlineKeyboardButton":
                # The portable renderer emits ``web_app`` as a plain dict, but
                # python-telegram-bot (>=20) requires a ``WebAppInfo`` object.
                web_app = btn.get("web_app")
                if isinstance(web_app, dict):
                    btn = {**btn, "web_app": WebAppInfo(**web_app)}
                return InlineKeyboardButton(**btn)

            rendered = TelegramPresentationRenderer.render(presentation)
            send_kwargs: Dict[str, Any] = {
                "chat_id": int(target),
                "text": rendered.get("text") or "\u200b",
            }
            reply_markup = rendered.get("reply_markup")
            inline_keyboard = (reply_markup or {}).get("inline_keyboard")
            if inline_keyboard:
                send_kwargs["reply_markup"] = InlineKeyboardMarkup(
                    [
                        [_build_button(btn) for btn in row]
                        for row in inline_keyboard
                    ]
                )
            message = await self._application.bot.send_message(**send_kwargs)
            return str(message.message_id)
        except Exception as e:
            logger.error(f"Failed to render presentation: {e}")
            return None


async def process_inbound_telegram_message(
    update,  # Telegram Update
    bot: TelegramBot,
    gateway_context: Optional[Dict] = None
) -> Optional[BotMessage]:
    """
    Shared security pipeline for processing inbound Telegram messages.
    
    Used by both standalone bot (TelegramBot.handle_message) and 
    gateway polling (_start_telegram_bot_polling) to ensure consistent
    access control enforcement.
    
    Args:
        update: Telegram Update object
        bot: TelegramBot instance with config and security settings
        gateway_context: Optional dict with gateway-specific context
        
    Returns:
        BotMessage if message passes all security checks, None if dropped
    """
    if not update.message:
        return None
    
    # Extract message text (including audio transcription)
    message_text = None
    if update.message.voice or update.message.audio:
        message_text = await bot._transcribe_audio(update)
    elif update.message.text:
        message_text = update.message.text
    elif update.message.photo or update.message.document:
        # Inbound photo/document (Issue #2350): use the caption as the prompt
        # so the message still flows through the security pipeline. The media
        # itself is downloaded and forwarded to the agent's vision capability
        # by the caller via TelegramBot._cache_inbound_telegram_media().
        message_text = update.message.caption or "[Media received]"

    if not message_text:
        return None
    
    # Convert to BotMessage for consistent processing
    message = bot._convert_update_to_message(update, override_text=message_text)
    
    # Set channel type for pairing system
    message._channel_type = "telegram"
    
    # Fire message received event (inbound gate: may drop or redact)
    if bot.fire_message_received(message).get("drop"):
        logger.debug("Message dropped by MESSAGE_RECEIVED hook")
        return None
    
    # 1. Channel allowlist check
    channel_id = message.channel.channel_id if message.channel else ""
    if not bot.config.is_channel_allowed(channel_id):
        logger.debug(f"Message dropped: channel {channel_id} not in allowed_channels")
        return None
    
    # 2. User allowlist and pairing check
    user_id = message.sender.user_id if message.sender else ""
    is_explicitly_allowed = bool(bot.config.allowed_users) and bot.config.is_user_allowed(user_id)
    
    if not is_explicitly_allowed:
        # Check if bot context is available for pairing system
        if not hasattr(bot, '_bot_context') or bot._bot_context is None:
            # For gateway mode, we need to create bot context on demand
            if not hasattr(bot, '_pairing_store'):
                from ..gateway.pairing import PairingStore
                bot._pairing_store = PairingStore()
            
            bot._bot_context = BotContext(
                config=bot.config,
                pairing_store=bot._pairing_store,
                adapter=bot
            )
        
        user_allowed = await UnknownUserHandler.handle(message, bot._bot_context)
        if not user_allowed:
            logger.debug(f"Message dropped: user {user_id} not allowed by pairing system")
            return None
    
    # 3. Group policy enforcement
    if message.channel and message.channel.channel_type not in ("dm", "private"):
        # This is a group/channel message, check group policies
        group_policy = getattr(bot.config, 'group_policy', 'mention_only')
        mention_required = getattr(bot.config, 'mention_required', True)
        
        if group_policy == "command_only":
            if message.message_type != MessageType.COMMAND:
                logger.debug(f"Message dropped: non-command in command_only group {channel_id}")
                return None
        elif group_policy == "mention_only":
            # Check if bot was mentioned in the message
            bot_username = bot._bot_user.username.lower() if bot._bot_user and bot._bot_user.username else ""
            mention_handle = f"@{bot_username}" if bot_username else ""
            bot_mentioned = (
                mention_handle and mention_handle in message.content.lower()
            ) or message.message_type == MessageType.COMMAND  # Commands are always allowed
            
            if not bot_mentioned:
                logger.debug(f"Message dropped: bot not mentioned in group {channel_id}")
                return None
        elif group_policy == "respond_all":
            # Allow all group messages
            pass
        elif mention_required:
            # Fallback for backward compatibility when group_policy is not set
            bot_username = bot._bot_user.username.lower() if bot._bot_user and bot._bot_user.username else ""
            mention_handle = f"@{bot_username}" if bot_username else ""
            bot_mentioned = (
                mention_handle and mention_handle in message.content.lower()
            ) or message.message_type == MessageType.COMMAND  # Commands are always allowed
            
            if not bot_mentioned:
                logger.debug(f"Message dropped: bot not mentioned in group {channel_id}")
                return None
    
    # All security checks passed
    logger.debug(f"Message security checks passed for user {user_id} in channel {channel_id}")
    return message
