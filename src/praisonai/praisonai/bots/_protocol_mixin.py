"""
Mixins for bot protocol implementations.

ChatCommandMixin — ``register_command`` / ``list_commands`` (DRY).
MessageHookMixin — fire MESSAGE_RECEIVED / MESSAGE_SENDING / MESSAGE_SENT hooks (DRY).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Set

from praisonaiagents.bots import ChatCommandInfo

logger = logging.getLogger(__name__)


class ChatCommandMixin:
    """Mixin that satisfies the ChatCommandProtocol interface.

    Expects the host class to have ``_command_handlers: Dict[str, Callable]``.

    Channel-specific command filtering:
        Pass ``channels=["telegram", "discord"]`` to ``register_command``
        to restrict a command to specific platforms.  If *channels* is
        empty/None the command is available everywhere.
    """

    _command_info: Dict[str, ChatCommandInfo]
    _command_channels: Dict[str, Set[str]]

    def register_command(
        self,
        name: str,
        handler: Callable,
        description: str = "",
        usage: Optional[str] = None,
        channels: Optional[List[str]] = None,
    ) -> None:
        """Register a chat command handler (ChatCommandProtocol).

        Args:
            name: Command name (without /).
            handler: Callable to invoke.
            description: Human-readable description.
            usage: Usage string shown in help.
            channels: Optional list of platform names this command is
                restricted to (e.g. ``["telegram", "slack"]``).
                ``None`` or ``[]`` means available on all platforms.
        """
        self._command_handlers[name] = handler  # type: ignore[attr-defined]
        if not hasattr(self, '_command_info'):
            self._command_info = {}
        if not hasattr(self, '_command_channels'):
            self._command_channels = {}
        self._command_info[name] = ChatCommandInfo(
            name=name, description=description, usage=usage
        )
        if channels:
            self._command_channels[name] = {c.lower() for c in channels}

    def list_commands(self, platform: Optional[str] = None) -> list:
        """List all registered chat commands (ChatCommandProtocol).

        Args:
            platform: If provided, only return commands available on
                this platform.  Builtins are always returned.
        """
        builtin_names = {"status", "new", "help"}
        builtins = [
            ChatCommandInfo(name="status", description="Show bot status and info"),
            ChatCommandInfo(name="new", description="Reset conversation session"),
            ChatCommandInfo(name="help", description="Show this help message"),
        ]
        custom_all = getattr(self, '_command_info', {})
        channels_map = getattr(self, '_command_channels', {})
        if platform:
            plat = platform.lower()
            custom = [
                info for name, info in custom_all.items()
                if name not in builtin_names and (name not in channels_map or plat in channels_map[name])
            ]
        else:
            custom = [
                info for name, info in custom_all.items()
                if name not in builtin_names
            ]
        return builtins + custom

    def is_command_allowed(self, name: str, platform: Optional[str] = None) -> bool:
        """Check if a command is allowed on the given platform."""
        channels_map = getattr(self, '_command_channels', {})
        if name not in channels_map:
            return True  # No restriction
        if not platform:
            return True
        return platform.lower() in channels_map[name]


class MessageHookMixin:
    """Mixin that fires MESSAGE_RECEIVED / MESSAGE_SENDING / MESSAGE_SENT hooks.

    All bot adapters inherit this so hook wiring is DRY.
    Expects the host class to have:
      - ``platform`` (str property)
      - ``_agent`` (optional Agent with hook_runner)

    Zero overhead when no hooks are registered — all attribute access
    is guarded by ``getattr`` checks.
    """

    def _get_hook_runner(self) -> Any:
        """Resolve the HookRunner from the agent, if available."""
        agent = getattr(self, '_agent', None)
        if agent is None:
            return None
        return getattr(agent, '_hook_runner', None)

    def fire_message_received(self, message: Any) -> None:
        """Fire MESSAGE_RECEIVED hook when an incoming message arrives.

        Args:
            message: A BotMessage instance.
        """
        runner = self._get_hook_runner()
        if runner is None:
            return
        try:
            from praisonaiagents.hooks.types import HookEvent
            from praisonaiagents.hooks.events import MessageReceivedInput

            platform = getattr(self, 'platform', 'unknown')
            sender = getattr(message, 'sender', None)
            channel = getattr(message, 'channel', None)
            content = getattr(message, 'content', '')
            if not isinstance(content, str):
                content = str(content)

            event_input = MessageReceivedInput(
                session_id="",
                cwd=os.getcwd(),
                event_name=HookEvent.MESSAGE_RECEIVED,
                timestamp=str(time.time()),
                agent_name=getattr(getattr(self, '_agent', None), 'agent_name', 'bot'),
                platform=platform,
                content=content,
                sender_id=getattr(sender, 'user_id', '') if sender else '',
                channel_id=getattr(channel, 'channel_id', '') if channel else '',
                channel_type=getattr(channel, 'channel_type', '') if channel else '',
                message_id=getattr(message, 'message_id', ''),
            )
            runner.execute_sync(HookEvent.MESSAGE_RECEIVED, event_input)
        except Exception as e:
            logger.debug(f"MESSAGE_RECEIVED hook error (non-fatal): {e}")

    def fire_message_sending(
        self, channel_id: str, content: str, reply_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fire MESSAGE_SENDING hook before sending a message.

        Hooks can modify content or cancel the send.

        Returns:
            dict with keys ``content`` (possibly modified) and ``cancel`` (bool).
        """
        result: Dict[str, Any] = {"content": content, "cancel": False}
        runner = self._get_hook_runner()
        if runner is None:
            return result
        try:
            from praisonaiagents.hooks.types import HookEvent
            from praisonaiagents.hooks.events import MessageSendingInput

            platform = getattr(self, 'platform', 'unknown')
            event_input = MessageSendingInput(
                session_id="",
                cwd=os.getcwd(),
                event_name=HookEvent.MESSAGE_SENDING,
                timestamp=str(time.time()),
                agent_name=getattr(getattr(self, '_agent', None), 'agent_name', 'bot'),
                platform=platform,
                content=content,
                channel_id=channel_id,
                reply_to=reply_to,
            )
            hook_results = runner.execute_sync(HookEvent.MESSAGE_SENDING, event_input)
            if runner.is_blocked(hook_results):
                result["cancel"] = True
                return result
            # Check for modified content in results
            if hook_results:
                for hr in hook_results:
                    output = getattr(hr, 'output', None)
                    if output is not None:
                        modified = getattr(output, 'modified_data', None)
                        if isinstance(modified, dict) and 'content' in modified:
                            result["content"] = modified["content"]
        except Exception as e:
            logger.debug(f"MESSAGE_SENDING hook error (non-fatal): {e}")
        return result

    def fire_message_sent(
        self, channel_id: str, content: str, message_id: str = ""
    ) -> None:
        """Fire MESSAGE_SENT hook after a message was successfully sent.

        Args:
            channel_id: The channel the message was sent to.
            content: The sent content.
            message_id: Platform message ID of the sent message.
        """
        runner = self._get_hook_runner()
        if runner is None:
            return
        try:
            from praisonaiagents.hooks.types import HookEvent
            from praisonaiagents.hooks.events import MessageSentInput

            platform = getattr(self, 'platform', 'unknown')
            event_input = MessageSentInput(
                session_id="",
                cwd=os.getcwd(),
                event_name=HookEvent.MESSAGE_SENT,
                timestamp=str(time.time()),
                agent_name=getattr(getattr(self, '_agent', None), 'agent_name', 'bot'),
                platform=platform,
                content=content,
                channel_id=channel_id,
                message_id=message_id,
            )
            runner.execute_sync(HookEvent.MESSAGE_SENT, event_input)
        except Exception as e:
            logger.debug(f"MESSAGE_SENT hook error (non-fatal): {e}")
