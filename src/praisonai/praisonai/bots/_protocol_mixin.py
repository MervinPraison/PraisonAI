"""
Mixin for ChatCommandProtocol implementation.

Provides ``register_command`` and ``list_commands`` so all bot
implementations share a single copy of the logic (DRY).

Also provides channel-specific command filtering via
``register_command(..., channels=[...])``.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Set

from praisonaiagents.bots import ChatCommandInfo


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
