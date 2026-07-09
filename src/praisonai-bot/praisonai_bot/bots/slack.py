"""
Slack Bot implementation for PraisonAI.

Provides a full Slack bot runtime with slash commands,
event handling, and agent integration.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
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
)
from ._session import BotSessionManager
from ._debounce import InboundDebouncer
from ._ack import AckReactor
from ._unknown_user import UnknownUserHandler, BotContext
from ._pairing_ui import PairingUIBuilder, PairingCallbackHandler
from ._outbound_resilience import OutboundResilienceMixin
from ..gateway.pairing import PairingStore

logger = logging.getLogger(__name__)


class SlackBot(OutboundResilienceMixin, ChatCommandMixin, MessageHookMixin):
    """Slack bot runtime for PraisonAI agents.
    
    Connects an agent to Slack, handling messages, slash commands,
    and providing full bot functionality.
    
    Example:
        from praisonai_bot.bots import SlackBot
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
    
    _outbound_platform = "slack"
    
    def __init__(
        self,
        token: str,
        app_token: Optional[str] = None,
        signing_secret: Optional[str] = None,
        agent: Optional["Agent"] = None,
        config: Optional[BotConfig] = None,
        **kwargs,
    ):
        """Initialize the Slack bot.
        
        Args:
            token: Slack bot token (xoxb-...)
            app_token: Slack app token for Socket Mode (xapp-...)
            signing_secret: Signing secret for webhook verification
            agent: Optional agent to handle messages
            config: Optional bot configuration
            **kwargs: Additional arguments for forward compatibility
        """
        # B9: Store extra kwargs for forward compatibility
        self._extra_kwargs = kwargs
        self._token = token
        self._app_token = app_token
        self._signing_secret = signing_secret
        self._agent = agent
        self.config = config or BotConfig(token=token)
        
        # Initialize allow_silence from config
        self._allow_silence = getattr(self.config, 'allow_silence', False)
        
        self._is_running = False
        self._bot_user: Optional[BotUser] = None
        self._app = None
        self._client = None
        
        self._message_handlers: List[Callable] = []
        self._command_handlers: Dict[str, Callable] = {}
        self._started_at: Optional[float] = None

        # Per-command authorization, shared with Telegram/Discord so privileged
        # commands (e.g. /learn) can be restricted consistently across channels.
        self._command_policy = build_command_access_policy(self.config)
        
        # Use helper to build session manager
        from ._session import build_session_manager
        self._session: BotSessionManager = build_session_manager(
            self.config,
            platform="slack"
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
        
        # Audio capabilities
        self._stt_enabled: bool = False
    
    def enable_stt(self, enabled: bool = True) -> None:
        """Enable STT for audio file transcription."""
        self._stt_enabled = enabled

    @staticmethod
    def _is_audio_file(f: Dict[str, Any]) -> bool:
        """Return True if a Slack file object looks like inbound audio.

        Slack sometimes tags voice notes with a generic mimetype (e.g.
        ``application/octet-stream``) while carrying a recognisable
        ``filetype``, so both are checked. Shared by transcription selection
        and the placeholder fallback so an audio-only message is never dropped
        for want of an ``audio/`` mimetype (Issue #2721).
        """
        mimetype = (f.get("mimetype") or "").lower()
        filetype = (f.get("filetype") or "").lower()
        return mimetype.startswith("audio/") or filetype in (
            "m4a", "mp3", "ogg", "wav", "opus", "webm", "mp4",
        )

    async def _transcribe_audio(self, event: Dict[str, Any]) -> Optional[str]:
        """Transcribe an inbound Slack voice/audio file (Issue #2721).

        Downloads the first audio file attached to the event via the bot token
        (``url_private_download``), caches it through the shared SSRF-safe media
        helper, and transcribes it with the shared STT tool. Returns the
        transcript, or ``None`` when STT is disabled, no audio is present, or
        transcription fails — callers fall back to a visible placeholder rather
        than dropping the message.
        """
        if not self._stt_enabled:
            return None

        files = event.get("files") or []
        audio_file = next((f for f in files if self._is_audio_file(f)), None)
        if audio_file is None:
            return None

        url = audio_file.get("url_private_download") or audio_file.get("url_private")
        if not url:
            return None

        try:
            import aiohttp

            from ._media import (
                cache_inbound_media,
                is_safe_url,
                resolve_max_inbound_media_bytes,
            )
            from ._stt import resolve_stt_config, transcribe_media_path

            max_bytes = resolve_max_inbound_media_bytes(self.config)
            if not max_bytes or max_bytes <= 0:
                return None

            # SSRF guard (Issue #2721): a forged Slack event could point
            # ``url_private_download`` at an internal address (e.g. cloud
            # metadata). Vet the host before fetching, mirroring the guard the
            # shared media cache applies to string-URL inputs.
            if not is_safe_url(url):
                logger.warning("Refusing to fetch unsafe Slack audio URL")
                return None

            token = getattr(self.config, "token", "") or ""
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        logger.warning("Slack audio download failed: HTTP %s", resp.status)
                        return None
                    data = await resp.content.read(max_bytes + 1)
            if len(data) > max_bytes:
                logger.warning("Inbound Slack audio exceeds %s bytes; skipping", max_bytes)
                return None

            path = cache_inbound_media(
                data,
                kind="audio",
                max_bytes=max_bytes,
                filename=audio_file.get("name"),
            )
            try:
                stt_cfg = resolve_stt_config(self.config)
                text = await asyncio.to_thread(
                    transcribe_media_path,
                    path,
                    language=stt_cfg.language,
                    model=stt_cfg.model,
                )
                if text and stt_cfg.echo_transcripts:
                    return f"[Voice message]: {text}"
                return text
            finally:
                try:
                    os.remove(path)
                except OSError:
                    pass
        except Exception as e:
            logger.error("Slack audio transcription error: %s", e)
            return None
    
    @property
    def is_running(self) -> bool:
        return self._is_running
    
    @property
    def platform(self) -> str:
        return "slack"
    
    @property
    def bot_user(self) -> Optional[BotUser]:
        return self._bot_user
    
    @property
    def capabilities(self) -> Dict[str, Any]:
        """Slack capabilities - supports edit and reactions, no typing."""
        return {
            "live_edit": True,
            "reactions": True,
            "typing": False,  # Slack doesn't support typing indicators via API
            "text_limit": 40000,  # Slack has a 40KB limit
            "edit_rate_limit": 1.0,
            "reaction_rate_limit": 0.5,
        }
    
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
        self._started_at = time.time()
        
        auth_response = await self._client.auth_test()
        self._bot_user = BotUser(
            user_id=auth_response["user_id"],
            username=auth_response["user"],
            display_name=auth_response.get("bot_id", auth_response["user"]),
            is_bot=True,
        )
        
        # Initialize bot context for pairing system
        self._bot_context = BotContext(
            config=self.config,
            pairing_store=self._pairing_store,
            adapter=self
        )
        
        @self._app.event("message")
        async def handle_message(event, say):
            if event.get("bot_id"):
                return
            
            bot_message = self._convert_event_to_message(event)

            # Issue #2721: transcribe an inbound voice/audio note so the turn
            # reaches the agent by voice. On disable/failure, fall back to a
            # visible placeholder instead of dropping an audio-only message.
            if not (bot_message.content or "").strip() and (event.get("files") or []):
                transcript = await self._transcribe_audio(event)
                if transcript:
                    bot_message.content = transcript
                elif any(
                    self._is_audio_file(f)
                    for f in (event.get("files") or [])
                ):
                    from ._stt import DEFAULT_VOICE_PLACEHOLDER
                    bot_message.content = DEFAULT_VOICE_PLACEHOLDER

            # Add channel type for pairing system
            bot_message._channel_type = "slack"
            
            decision = self.fire_message_received(bot_message)
            if decision.get("drop"):
                logger.debug("Message dropped by MESSAGE_RECEIVED hook")
                return
            
            # Check if channel is allowed
            if not self.config.is_channel_allowed(bot_message.channel.channel_id if bot_message.channel else ""):
                return
            
            # Handle unknown users with pairing system
            user_id = bot_message.sender.user_id if bot_message.sender else ""
            is_explicitly_allowed = self.config.is_explicitly_allowed(user_id)
            if not is_explicitly_allowed:
                user_allowed = await UnknownUserHandler.handle(bot_message, self._bot_context)
                if not user_allowed:
                    return
            
            # Use the (possibly redacted) content from the inbound gate rather
            # than the raw Slack event so a MESSAGE_RECEIVED hook that rewrites
            # content (e.g. PII redaction) actually reaches command parsing and
            # agent dispatch.
            text = (decision.get("content") or bot_message.content or "").strip()
            # Per-command authorization: privileged commands (e.g. /learn) can be
            # restricted to admins independent of the channel/pairing allow gate,
            # consistent with Telegram and Discord.
            if text.startswith("/"):
                command_name = text[1:].split(maxsplit=1)[0].lower() if len(text) > 1 else ""
                cmd_user_id = event.get("user", "unknown")
                if command_name and not self._command_policy.can_run(cmd_user_id, command_name):
                    await say(
                        text=f"⛔ You are not permitted to run /{command_name}",
                        thread_ts=event.get("ts"),
                    )
                    return
            if text == "/status":
                await say(text=self._format_status(), thread_ts=event.get("ts"))
                return
            elif text == "/new":
                user_id = event.get("user", "unknown")
                # Pass the chat route so a /new in a channel/group clears the
                # shared per_chat session (Issue #2376); a no-op for per_user.
                self._session.reset(
                    user_id,
                    account=getattr(self.config, "account", "default"),
                    chat_id=str(event.get("channel", "")),
                    thread_id=event.get("thread_ts", "") or "",
                )
                await say(text="Session reset. Starting fresh conversation.", thread_ts=event.get("ts"))
                return
            elif text == "/help":
                await say(text=self._format_help(), thread_ts=event.get("ts"))
                return
            elif text == "/stop":
                user_id = event.get("user", "unknown")
                response = handle_stop_command(self._session, user_id)
                await say(text=response, thread_ts=event.get("ts"))
                return
            elif text.split(maxsplit=1)[:1] == ["/model"]:
                user_id = event.get("user", "unknown")
                parts = text.split(maxsplit=1)
                model_name = parts[1] if len(parts) > 1 else None
                response = handle_model_command(self._session, user_id, model_name, self._agent)
                await say(text=response, thread_ts=event.get("ts"))
                return
            elif text == "/usage":
                user_id = event.get("user", "unknown")
                response = handle_usage_command(self._session, user_id, self._agent)
                await say(text=response, thread_ts=event.get("ts"))
                return
            elif text == "/compress":
                user_id = event.get("user", "unknown")
                response = handle_compress_command(self._session, user_id, self._agent)
                await say(text=response, thread_ts=event.get("ts"))
                return
            elif text.split(maxsplit=1)[:1] == ["/queue"]:
                user_id = event.get("user", "unknown")
                parts = text.split(maxsplit=1)
                message_text = parts[1] if len(parts) > 1 else None
                response = handle_queue_command(self._session, user_id, message_text)
                await say(text=response, thread_ts=event.get("ts"))
                return
            elif text.split(maxsplit=1)[:1] == ["/learn"]:
                parts = text.split(maxsplit=1)
                request = parts[1] if len(parts) > 1 else None
                response = handle_learn_command(self._agent, request)
                await say(text=response, thread_ts=event.get("ts"))
                return
            elif text == "/undo":
                response = handle_undo_command(self._agent)
                await say(text=response, thread_ts=event.get("ts"))
                return
            elif text == "/sessions":
                user_id = event.get("user", "unknown")
                response = handle_sessions_command(self._session, user_id)
                await say(text=response, thread_ts=event.get("ts"))
                return
            elif text.split(maxsplit=1)[:1] == ["/resume"]:
                user_id = event.get("user", "unknown")
                parts = text.split(maxsplit=1)
                session_id = parts[1] if len(parts) > 1 else None
                response = handle_resume_command(self._session, user_id, session_id)
                await say(text=response, thread_ts=event.get("ts"))
                return
            elif text == "/retry":
                user_id = event.get("user", "unknown")
                last_user_msg = get_last_user_message(self._session, user_id)
                if not last_user_msg:
                    await say(
                        text="ℹ️ Nothing to retry — no previous message found.",
                        thread_ts=event.get("ts"),
                    )
                    return
                await say(text="🔁 Retrying your last message…", thread_ts=event.get("ts"))
                try:
                    response = await self._session.chat(
                        self._agent, user_id, last_user_msg,
                        chat_id=str(event.get("channel", "")),
                        thread_id=event.get("thread_ts", "") or "",
                        message_id=event.get("ts", ""),
                        account=getattr(self.config, "account", "default"),
                    )
                    await say(text=response, thread_ts=event.get("ts"))
                except Exception as e:  # noqa: BLE001 - surface a friendly message
                    logger.warning("retry failed: %s", e)
                    await say(text=f"❌ Retry failed: {e}", thread_ts=event.get("ts"))
                return
            elif text == "/reasoning":
                user_id = event.get("user", "unknown")
                response = handle_reasoning_command(self._session, user_id, self._agent)
                await say(text=response, thread_ts=event.get("ts"))
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
            # Dispatch the (possibly redacted) content from the inbound gate so
            # a MESSAGE_RECEIVED hook rewrite reaches the agent, not the raw text.
            text = decision.get("content") or bot_message.content or ""
            channel_type = event.get("channel_type", "")
            
            if channel_type == "im":
                should_respond = True
            elif self._bot_user and f"<@{self._bot_user.user_id}>" in text:
                should_respond = True
                text = text.replace(f"<@{self._bot_user.user_id}>", "").strip()
            elif not self.config.mention_required:
                should_respond = True
            
            if should_respond and self._agent:
                channel_id = event.get("channel", "")
                msg_ts = event.get("ts", "")
                
                # Ack reaction - show processing indicator
                ack_ctx = None
                if self._ack.enabled and self._client:
                    async def _slack_react(emoji, **kw):
                        try:
                            # Slack uses emoji names without colons
                            emoji_name = emoji.strip(":")
                            await self._client.reactions_add(
                                channel=channel_id,
                                timestamp=msg_ts,
                                name=emoji_name,
                            )
                        except Exception:
                            pass  # Reactions may fail silently
                    async def _slack_unreact(emoji, **kw):
                        try:
                            emoji_name = emoji.strip(":")
                            await self._client.reactions_remove(
                                channel=channel_id,
                                timestamp=msg_ts,
                                name=emoji_name,
                            )
                        except Exception:
                            pass
                    ack_ctx = await self._ack.ack(react_fn=_slack_react)
                
                try:
                    user_id = event.get("user", "unknown")
                    logger.info(f"Message received: {text[:100]}...")
                    text = await self._debouncer.debounce(user_id, text)
                    response = await self._session.chat(
                        self._agent, user_id, text,
                        chat_id=str(channel_id) if channel_id else "",
                        thread_id=event.get("thread_ts", "") or "",
                        message_id=event.get("ts", ""),
                        account=getattr(self.config, "account", "default"),
                    )
                    logger.info(f"Response sent: {response[:100]}...")
                    
                    send_result = self.fire_message_sending(channel_id, str(response))
                    if send_result["cancel"]:
                        return
                    response = send_result["content"]
                    
                    # Determine if we should reply in thread
                    thread_ts = None
                    if self.config.reply_in_thread:
                        thread_ts = event.get("thread_ts") or event.get("ts")
                    elif self.config.thread_threshold > 0 and len(response) > self.config.thread_threshold:
                        # Auto-thread long responses
                        thread_ts = event.get("thread_ts") or event.get("ts")
                    
                    await self._send_response_with_media(
                        channel_id, say, response, thread_ts=thread_ts
                    )
                    self.fire_message_sent(channel_id, response)
                    
                    # Done reaction - show completion
                    if ack_ctx and self._client:
                        await self._ack.done(ack_ctx, react_fn=_slack_react, unreact_fn=_slack_unreact)
                except Exception as e:
                    logger.error(f"Agent error: {e}")
                    error_msg = str(e)
                    if error_msg:
                        await say(text=f"Error: {error_msg}", thread_ts=event.get("ts"))
        
        @self._app.event("app_mention")
        async def handle_mention(event, say):
            if event.get("bot_id"):
                return

            bot_message = self._convert_event_to_message(event)
            bot_message._channel_type = "slack"

            if not self.config.is_channel_allowed(
                bot_message.channel.channel_id if bot_message.channel else ""
            ):
                return

            user_id = bot_message.sender.user_id if bot_message.sender else ""
            is_explicitly_allowed = self.config.is_explicitly_allowed(user_id)
            if not is_explicitly_allowed:
                user_allowed = await UnknownUserHandler.handle(bot_message, self._bot_context)
                if not user_allowed:
                    return
            
            text = event.get("text", "")
            if self._bot_user:
                text = text.replace(f"<@{self._bot_user.user_id}>", "").strip()
            
            if self._agent:
                try:
                    user_id = event.get("user", "unknown")
                    logger.info(f"@mention received: {text[:100]}...")
                    response = await self._session.chat(
                        self._agent, user_id, text,
                        chat_id=str(event.get("channel", "")),
                        thread_id=event.get("thread_ts", "") or "",
                        message_id=event.get("ts", ""),
                        account=getattr(self.config, "account", "default"),
                    )
                    logger.info(f"Response sent: {response[:100]}...")
                    
                    # Check for silence
                    send_result = self.fire_message_sending(event.get("channel", ""), str(response))
                    if send_result.get("cancel"):
                        return
                    response = send_result.get("content", response)
                    
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
                # Per-command authorization for registered slash commands, mirroring
                # the message-event gate so privileged commands can't bypass policy.
                if not self._command_policy.can_run(
                    command_data.get("user_id", ""), cmd
                ):
                    await respond(f"⛔ You are not permitted to run /{cmd}")
                    return
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
        
        # Add generic block action handler for all interactive buttons
        @self._app.action(re.compile(".*"))
        async def handle_block_actions(ack, body, action):
            await ack()
            
            # Extract callback data from button value
            callback_data = action.get("value", action.get("action_id", ""))
            if not callback_data:
                return
            
            # Create interactive context
            from praisonaiagents.bots import InteractiveContext
            ctx = InteractiveContext(
                callback_data=callback_data,
                user_id=body["user"]["id"],
                message_id=body["message"]["ts"] if "message" in body else None,
                chat_id=body["channel"]["id"] if "channel" in body else None,
                bot_adapter=self,
                platform_data={
                    "body": body,
                    "action": action,
                }
            )
            
            # Try to dispatch through the interactive registry
            handled = await self._interactive_registry.dispatch(ctx)
            
            if not handled:
                # Fallback: handle legacy pairing callbacks
                if callback_data.startswith("pair:"):
                    result = await self._pairing_callback_handler.handle_approval_callback(
                        callback_data=callback_data,
                        owner_user_id=body["user"]["id"],
                        bot_adapter=self
                    )
                    
                    # Update the message
                    blocks = body["message"]["blocks"]
                    # Remove the action block
                    blocks = [block for block in blocks if block["type"] != "actions"]
                    # Add result message
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn", 
                            "text": result.message
                        }
                    })
                    
                    try:
                        await self._client.chat_update(
                            channel=body["channel"]["id"],
                            ts=body["message"]["ts"],
                            blocks=blocks,
                            text=body["message"]["text"]
                        )
                    except Exception as e:
                        logger.error(f"Failed to update message: {e}")
                else:
                    logger.debug(f"Unhandled callback: {callback_data}")
        
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
        self._debouncer.cancel_all()
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
        
        # Durable delivery: retry transient failures with backoff and park the
        # reply in the outbound DLQ on permanent failure instead of dropping it.
        send_kwargs = dict(kwargs)
        response = await self.deliver_outbound(
            lambda: self._client.chat_postMessage(**send_kwargs),
            channel_id=channel_id,
            reply_text=text,
            thread_id=thread_id,
            reply_to=reply_to,
        )
        
        return BotMessage(
            message_id=response["ts"],
            content=text,
            message_type=MessageType.TEXT,
            channel=BotChannel(channel_id=channel_id),
        )
    
    async def _send_long_message(self, say, text: str, thread_ts: Optional[str] = None) -> None:
        """Send a long message, splitting with markdown-aware chunking."""
        from ._chunk import chunk_message

        max_len = min(self.config.max_message_length, 4000)
        
        if not text or not text.strip():
            logger.warning("Attempted to send empty message")
            return

        if len(text) <= max_len:
            await say(text=text.strip(), thread_ts=thread_ts)
        else:
            chunks = chunk_message(text, max_length=max_len, preserve_fences=True)
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
    
    async def add_reaction(self, channel_id: str, message_id: str, emoji: str) -> bool:
        """Add a reaction to a message."""
        if not self._client:
            return False
        
        try:
            # Map common Unicode emojis to Slack names
            emoji_mapping = {
                "🤔": "thinking_face",
                "⏳": "hourglass",
                "🔧": "wrench",
                "✅": "white_check_mark",
                "❌": "x",
            }
            
            # If it's a Unicode emoji, try to map it
            if emoji in emoji_mapping:
                emoji_name = emoji_mapping[emoji]
            else:
                # Otherwise strip colons if present (for :emoji_name: format)
                emoji_name = emoji.strip(':')
            
            await self._client.reactions_add(
                channel=channel_id,
                timestamp=message_id,
                name=emoji_name,
            )
            return True
        except Exception as e:
            logger.debug(f"Failed to add reaction: {e}")
            return False
    
    async def remove_reaction(self, channel_id: str, message_id: str, emoji: str) -> bool:
        """Remove a reaction from a message."""
        if not self._client:
            return False
        
        try:
            # Map common Unicode emojis to Slack names
            emoji_mapping = {
                "🤔": "thinking_face",
                "⏳": "hourglass",
                "🔧": "wrench",
                "✅": "white_check_mark",
                "❌": "x",
            }
            
            # If it's a Unicode emoji, try to map it
            if emoji in emoji_mapping:
                emoji_name = emoji_mapping[emoji]
            else:
                # Otherwise strip colons if present (for :emoji_name: format)
                emoji_name = emoji.strip(':')
            
            await self._client.reactions_remove(
                channel=channel_id,
                timestamp=message_id,
                name=emoji_name,
            )
            return True
        except Exception as e:
            logger.debug(f"Failed to remove reaction: {e}")
            return False
    
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
    
    async def probe(self):
        """Test Slack API connectivity without starting the bot."""
        from praisonaiagents.bots import ProbeResult
        started = time.time()
        try:
            import aiohttp
            url = "https://slack.com/api/auth.test"
            headers = {"Authorization": f"Bearer {self._token}"}
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    elapsed = (time.time() - started) * 1000
                    if data.get("ok"):
                        return ProbeResult(
                            ok=True, platform="slack", elapsed_ms=elapsed,
                            bot_username=data.get("user"),
                            details={"team": data.get("team"), "team_id": data.get("team_id"), "user_id": data.get("user_id")},
                        )
                    else:
                        return ProbeResult(ok=False, platform="slack", elapsed_ms=elapsed, error=data.get("error", "Unknown error"))
        except Exception as e:
            return ProbeResult(ok=False, platform="slack", elapsed_ms=(time.time() - started) * 1000, error=str(e))

    async def health(self):
        """Get detailed health status of the Slack bot."""
        return await self._default_health()

    def _format_status(self) -> str:
        """Format /status response."""
        return format_status(self._agent, self.platform, self._started_at, self._is_running)
    
    def _format_help(self) -> str:
        """Format /help response."""
        extra = {cmd: "Custom command" for cmd in self._command_handlers}
        return format_help(self._agent, self.platform, extra)
    
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
    
    # Adapter methods for pairing system
    def _register_interactive_handlers(self):
        """Register handlers for interactive callbacks."""
        registry = self._interactive_registry
        
        # Register handler for command callbacks
        async def handle_command_callback(ctx):
            """Handle command callbacks from buttons."""
            payload = ctx.platform_data.get("decoded_payload", {})
            command = payload.get("command", "")
            
            # Get the Slack body and action objects
            body = ctx.platform_data.get("body")
            action = ctx.platform_data.get("action")
            if not body or not action:
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
                        message_id=body.get("message", {}).get("ts", ""),
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
                    if "message" in body:
                        blocks = body["message"]["blocks"]
                        blocks = [block for block in blocks if block["type"] != "actions"]
                        blocks.append({
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"✅ Command executed: /{cmd_name}"
                            }
                        })
                        
                        await self._client.chat_update(
                            channel=body["channel"]["id"],
                            ts=body["message"]["ts"],
                            blocks=blocks,
                            text=body["message"]["text"]
                        )
                    return f"Command {cmd_name} executed"
                except Exception as e:
                    logger.error(f"Command handler error: {e}")
                    return f"Error: {e}"
            
            logger.debug(f"Unknown command from button: {cmd_name}")
            return None
        
        # Register the command handler
        registry.register("command", handle_command_callback)
        
        # Register handler for pairing callbacks using the new system
        async def handle_pairing_callback(ctx):
            """Handle pairing callbacks through the new registry."""
            body = ctx.platform_data.get("body")
            if not body:
                return None
            
            # The pairing handler already exists, we just wrap it
            result = await self._pairing_callback_handler.handle_approval_callback(
                callback_data=ctx.callback_data,
                owner_user_id=ctx.user_id,
                bot_adapter=self
            )
            
            # Update the message with result
            if "message" in body:
                blocks = body["message"]["blocks"]
                blocks = [block for block in blocks if block["type"] != "actions"]
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": result.message
                    }
                })
                
                await self._client.chat_update(
                    channel=body["channel"]["id"],
                    ts=body["message"]["ts"],
                    blocks=blocks,
                    text=body["message"]["text"]
                )
            
            return f"Pairing {result.action}"
        
        # Register the pairing handler
        registry.register("pair", handle_pairing_callback)
    
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
            blocks = PairingUIBuilder.create_slack_blocks(
                user_name=user_name,
                code=code,
                channel=channel,
                user_id=user_id
            )
            
            # Send direct message
            response = await self._client.chat_postMessage(
                channel=owner_user_id,
                text=f"{user_name} wants to chat. Approve access?",
                blocks=blocks
            )
            
            return response["ts"]
            
        except Exception as e:
            logger.error(f"Failed to send approval DM: {e}")
            return None
    
    async def reply(self, chat_id: str, text: str) -> None:
        """Reply to a chat/DM with a text message."""
        if not self._client:
            return
        
        try:
            await self._client.chat_postMessage(
                channel=chat_id,
                text=text
            )
        except Exception as e:
            logger.error(f"Failed to send reply: {e}")
