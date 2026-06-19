"""
Status reaction and indication helpers for bot channels.

Provides unified status feedback through reactions or status lines,
showing agent execution progress with debouncing and terminal state handling.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents.bots.protocols import RunStatus, ChannelCapabilities

logger = logging.getLogger(__name__)


class BotAdapter(Protocol):
    """Protocol for bot adapters that support reactions."""
    
    @property
    def capabilities(self) -> "ChannelCapabilities":
        """Get channel capabilities."""
        ...
    
    async def add_reaction(self, channel_id: str, message_id: str, emoji: str) -> bool:
        """Add a reaction to a message."""
        ...
    
    async def remove_reaction(self, channel_id: str, message_id: str, emoji: str) -> bool:
        """Remove a reaction from a message."""
        ...


@dataclass
class StatusConfig:
    """Configuration for status feedback."""
    
    # Status emoji mappings
    queued_emoji: str = "⏳"
    thinking_emoji: str = "🤔"
    tool_emoji: str = "🔧"
    done_emoji: str = "✅"
    error_emoji: str = "❌"
    
    # Debounce settings
    debounce_delay: float = 0.5  # Seconds to wait before applying intermediate status
    immediate_terminal: bool = True  # Apply terminal states (done/error) immediately
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StatusConfig":
        """Create config from dictionary."""
        return cls(
            queued_emoji=data.get("queued_emoji", "⏳"),
            thinking_emoji=data.get("thinking_emoji", "🤔"),
            tool_emoji=data.get("tool_emoji", "🔧"),
            done_emoji=data.get("done_emoji", "✅"),
            error_emoji=data.get("error_emoji", "❌"),
            debounce_delay=data.get("debounce_delay", 0.5),
            immediate_terminal=data.get("immediate_terminal", True),
        )


class StatusReactions:
    """
    Manages status feedback through reactions or status lines.
    
    Provides a unified interface for showing agent execution progress,
    with debouncing for intermediate states and immediate application
    of terminal states.
    
    Usage:
        status = StatusReactions(
            adapter=bot_adapter,
            channel_id="123456",
            message_id="789",
            config=StatusConfig()
        )
        
        await status.set("thinking")  # Debounced
        await status.set("tool")      # Debounced, may coalesce
        await status.set("done")      # Immediate
    """
    
    def __init__(
        self,
        adapter: BotAdapter,
        channel_id: str,
        message_id: str,
        config: Optional[StatusConfig] = None,
    ):
        self._adapter = adapter
        self._channel_id = channel_id
        self._message_id = message_id
        self._config = config or StatusConfig()
        
        # State
        self._current_status: Optional[str] = None
        self._current_emoji: Optional[str] = None
        self._pending_status: Optional[str] = None
        self._update_task: Optional[asyncio.Task] = None
        
        # Check if reactions are supported
        caps = adapter.capabilities
        self._enabled = caps.get("reactions", False)
        
        logger.debug(
            "StatusReactions initialized for message %s, reactions_enabled=%s",
            message_id, self._enabled
        )
    
    def _get_emoji(self, status: str) -> str:
        """Get emoji for a status."""
        from praisonaiagents.bots.protocols import RunStatus
        
        mapping = {
            RunStatus.QUEUED.value: self._config.queued_emoji,
            RunStatus.THINKING.value: self._config.thinking_emoji,
            RunStatus.TOOL.value: self._config.tool_emoji,
            RunStatus.DONE.value: self._config.done_emoji,
            RunStatus.ERROR.value: self._config.error_emoji,
        }
        return mapping.get(status, self._config.thinking_emoji)
    
    def _is_terminal(self, status: str) -> bool:
        """Check if status is terminal (done/error)."""
        from praisonaiagents.bots.protocols import RunStatus
        
        return status in (RunStatus.DONE.value, RunStatus.ERROR.value)
    
    async def set(self, status: str) -> None:
        """Set the current status.
        
        Intermediate states are debounced to avoid excessive updates.
        Terminal states (done/error) are applied immediately.
        
        Args:
            status: Status to set (from RunStatus enum values)
        """
        if not self._enabled:
            return
        
        # Skip if same status
        if status == self._current_status:
            return
        
        self._pending_status = status
        
        # Apply terminal states immediately
        if self._is_terminal(status) and self._config.immediate_terminal:
            # Cancel any pending update
            if self._update_task and not self._update_task.done():
                self._update_task.cancel()
                try:
                    await self._update_task
                except asyncio.CancelledError:
                    pass
            
            await self._apply_status(status)
            return
        
        # Debounce intermediate states
        if self._update_task and not self._update_task.done():
            # Update already scheduled, new status will be picked up
            return
        
        # Schedule debounced update
        async def _delayed_update():
            await asyncio.sleep(self._config.debounce_delay)
            # Save the pending status to apply (may have changed during sleep)
            status_to_apply = self._pending_status
            if status_to_apply:
                await self._apply_status(status_to_apply)
        
        self._update_task = asyncio.create_task(_delayed_update())
    
    async def _apply_status(self, status: str) -> None:
        """Apply a status change."""
        emoji = self._get_emoji(status)
        
        try:
            # Remove previous emoji if different
            if self._current_emoji and self._current_emoji != emoji:
                await self._adapter.remove_reaction(
                    self._channel_id,
                    self._message_id,
                    self._current_emoji
                )
                # Clear current emoji after successful removal
                self._current_emoji = None
            
            # Add new emoji
            if emoji:
                success = await self._adapter.add_reaction(
                    self._channel_id,
                    self._message_id,
                    emoji
                )
                
                if success:
                    self._current_status = status
                    self._current_emoji = emoji
                    
                    logger.debug(
                        "StatusReactions applied %s (%s) to message %s",
                        status, emoji, self._message_id
                    )
                else:
                    # Failed to add reaction, but we already removed the old one
                    # Keep state consistent
                    self._current_status = None
                    logger.debug(
                        "StatusReactions failed to add reaction %s to message %s",
                        emoji, self._message_id
                    )
            
            # Only clear pending status if we applied it successfully
            # (or if there's no emoji to apply)
            if status == self._pending_status:
                self._pending_status = None
            
        except Exception as e:
            logger.warning("StatusReactions failed to apply status: %s", e)
            # On exception, clear emoji state to avoid desync
            self._current_emoji = None
            self._current_status = None
    
    async def clear(self) -> None:
        """Clear all status reactions."""
        if not self._enabled or not self._current_emoji:
            return
        
        # Cancel pending updates
        if self._update_task and not self._update_task.done():
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        
        try:
            await self._adapter.remove_reaction(
                self._channel_id,
                self._message_id,
                self._current_emoji
            )
            self._current_status = None
            self._current_emoji = None
            self._pending_status = None
            
        except Exception as e:
            logger.warning("StatusReactions failed to clear: %s", e)