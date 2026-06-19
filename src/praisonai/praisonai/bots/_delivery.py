"""
Unified message delivery for PraisonAI bots.

Uses platform capabilities to apply features like streaming, chunking, 
and rate limiting uniformly across all platforms.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional, Union, Dict, Any, List

if TYPE_CHECKING:
    from praisonaiagents.bots import BotProtocol, PlatformCapabilities

from ._chunk import chunk_message, _calculate_length
from ._streaming import DraftStreamer, StreamingConfig, StreamingMode
from ._rate_limit import RateLimiter

logger = logging.getLogger(__name__)


class UnifiedDelivery:
    """Unified message delivery that adapts to platform capabilities.
    
    This class demonstrates how platform capabilities enable uniform
    feature delivery across all bot adapters.
    """
    
    def __init__(self, bot: "BotProtocol"):
        """Initialize with a bot instance.
        
        Args:
            bot: Bot adapter implementing BotProtocol
        """
        self.bot = bot
        self._capabilities: Optional["PlatformCapabilities"] = None
        self._rate_limiter: Optional[RateLimiter] = None
        self._streamer: Optional[DraftStreamer] = None
    
    @property
    def capabilities(self) -> "PlatformCapabilities":
        """Get platform capabilities (cached)."""
        if self._capabilities is None:
            # Use platform_capabilities property from the updated protocol
            self._capabilities = self.bot.platform_capabilities
        return self._capabilities
    
    async def send_message(
        self,
        channel_id: str,
        content: Union[str, Dict[str, Any]],
        stream: bool = False,
        typing: bool = True,
        **kwargs,
    ) -> List[Any]:
        """Send a message with platform-aware features.
        
        Args:
            channel_id: Target channel ID
            content: Message content
            stream: Whether to use streaming if supported
            typing: Whether to show typing indicator
            **kwargs: Additional platform-specific arguments
            
        Returns:
            List of sent messages (may be multiple due to chunking)
        """
        caps = self.capabilities
        text = content if isinstance(content, str) else str(content)
        
        # Show typing indicator if supported
        if typing and caps.supports_typing:
            asyncio.create_task(self._show_typing(channel_id))
        
        # Check if we should stream
        if stream and caps.supports_edit and _calculate_length(text, caps.length_unit) > caps.max_message_length // 2:
            # Use streaming for long messages on platforms that support edits
            return await self._send_streamed(channel_id, text, **kwargs)
        
        # Chunk the message based on platform limits
        chunks = chunk_message(
            text,
            max_length=caps.max_message_length,
            length_unit=caps.length_unit,
            preserve_fences=True,
        )
        
        # Send each chunk
        messages = []
        for chunk in chunks:
            # Apply rate limiting per chunk
            if caps.needs_rate_limit:
                await self._acquire_rate_limit()
            
            msg = await self.bot.send_message(channel_id, chunk, **kwargs)
            messages.append(msg)
        
        return messages
    
    async def _send_streamed(
        self,
        channel_id: str,
        text: str,
        **kwargs,
    ) -> List[Any]:
        """Send a message using streaming/progressive edits.
        
        Args:
            channel_id: Target channel ID
            text: Full message text
            **kwargs: Additional arguments
            
        Returns:
            List containing the final message
        """
        caps = self.capabilities
        
        if self._streamer is None:
            config = StreamingConfig(
                mode=StreamingMode.DRAFT,
                min_interval=caps.edit_interval_ms / 1000.0,
                min_delta=50,
            )
            self._streamer = DraftStreamer(self.bot, config)
        
        # Send initial placeholder
        message = await self.bot.send_message(
            channel_id,
            "🤔 Thinking...",
            **kwargs,
        )
        messages = [message]  # Initialize messages list for returning
        
        # Progressively update with content using proper length calculation
        chunk_size = min(100, caps.max_message_length // 10)
        current_pos = 0
        
        # Stream partial content
        while current_pos < len(text):
            # Calculate next position based on platform's length unit
            next_pos = current_pos + chunk_size
            if next_pos > len(text):
                next_pos = len(text)
            
            partial = text[:next_pos]
            
            # Check if partial exceeds platform limit
            if _calculate_length(partial, caps.length_unit) > caps.max_message_length:
                # Back off to find safe length
                while next_pos > current_pos and _calculate_length(text[:next_pos], caps.length_unit) > caps.max_message_length:
                    next_pos -= 10
                if next_pos <= current_pos:
                    break  # Can't fit more content
                partial = text[:next_pos]
            
            # Respect edit interval
            await asyncio.sleep(caps.edit_interval_ms / 1000.0)
            
            # Apply rate limiting for edits
            if caps.needs_rate_limit:
                await self._acquire_rate_limit()
            
            # Add ellipsis if not complete
            display_text = partial if next_pos >= len(text) else partial + "..."
            
            await self.bot.edit_message(
                channel_id,
                message.message_id,
                display_text,
            )
            
            if next_pos >= len(text):
                break  # Complete text has been sent
            
            current_pos = next_pos
        
        # If text is too long and couldn't fit in one message, chunk it
        if _calculate_length(text, caps.length_unit) > caps.max_message_length:
            # Final content needs chunking
            chunks = chunk_message(
                text,
                max_length=caps.max_message_length,
                length_unit=caps.length_unit,
                preserve_fences=True,
            )
            
            # Edit first message with first chunk
            await asyncio.sleep(caps.edit_interval_ms / 1000.0)
            if caps.needs_rate_limit:
                await self._acquire_rate_limit()
            
            await self.bot.edit_message(
                channel_id,
                message.message_id,
                chunks[0],
            )
            
            # Send remaining chunks as new messages
            for chunk in chunks[1:]:
                if caps.needs_rate_limit:
                    await self._acquire_rate_limit()
                msg = await self.bot.send_message(channel_id, chunk)
                messages.append(msg)
        else:
            # Final edit with complete content (fits in limit)
            await asyncio.sleep(caps.edit_interval_ms / 1000.0)
            if caps.needs_rate_limit:
                await self._acquire_rate_limit()
            
            await self.bot.edit_message(
                channel_id,
                message.message_id,
                text,
            )
        
        return messages
    
    async def _show_typing(self, channel_id: str) -> None:
        """Show typing indicator for a few seconds.
        
        Args:
            channel_id: Target channel ID
        """
        try:
            for _ in range(3):  # Show for ~3 seconds
                await self.bot.send_typing(channel_id)
                await asyncio.sleep(1)
        except Exception as e:
            logger.debug("Could not show typing indicator: %s", e)
    
    async def _acquire_rate_limit(self) -> None:
        """Acquire rate limit token if platform needs it."""
        if self._rate_limiter is None:
            # Use platform-specific rate limiter
            self._rate_limiter = RateLimiter.for_platform(self.bot.platform)
        
        if self._rate_limiter:
            await self._rate_limiter.acquire()


def create_delivery(bot: "BotProtocol") -> UnifiedDelivery:
    """Create a unified delivery instance for a bot.
    
    Args:
        bot: Bot adapter
        
    Returns:
        UnifiedDelivery instance configured for the bot's platform
    """
    return UnifiedDelivery(bot)