"""
Progressive streaming for channel bots.

Bridges Agent.stream_emitter events to progressive message editing,
enabling live token-by-token response delivery instead of blocking
single messages.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents.streaming.events import StreamEvent, StreamEventEmitter

logger = logging.getLogger(__name__)


@dataclass
class StreamEditState:
    """Tracks progressive edit state for a streaming response."""
    message_id: str
    accumulated_content: str = ""
    last_edit_time: float = 0.0
    total_edits: int = 0
    is_finalized: bool = False


class ChannelStreamConsumer:
    """
    Bridges Agent.stream_emitter deltas to progressive adapter edits.
    
    Subscribes to streaming events from an agent during bot interactions
    and progressively edits a placeholder message as tokens arrive.
    
    Features:
    - Configurable minimum edit interval (respects platform rate limits)
    - Markdown/code-fence-safe partial rendering
    - Overflow handling for platform message limits
    - Graceful fallback when edits are unsupported
    """
    
    def __init__(
        self,
        adapter: Any,  # Bot adapter with edit_message method
        channel_id: str,
        *,
        edit_interval_ms: int = 700,
        max_message_length: int = 4096,
        platform: str = "unknown",
    ):
        """
        Initialize the stream consumer.
        
        Args:
            adapter: Bot adapter instance with edit_message method
            channel_id: Platform channel/chat ID
            edit_interval_ms: Minimum milliseconds between edits
            max_message_length: Platform message length limit
            platform: Platform name for logging
        """
        self._adapter = adapter
        self._channel_id = channel_id
        self._edit_interval_ms = edit_interval_ms
        self._max_message_length = max_message_length
        self._platform = platform
        
        self._state: Optional[StreamEditState] = None
        self._pending_edit_task: Optional[asyncio.Task] = None
        self._emitter: Optional["StreamEventEmitter"] = None
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Check if adapter supports editing
        self._supports_editing = hasattr(adapter, 'edit_message') and callable(adapter.edit_message)
        
        if not self._supports_editing:
            logger.debug("Adapter %s does not support edit_message, streaming disabled", 
                        type(adapter).__name__)
    
    @property
    def supports_streaming(self) -> bool:
        """Whether this consumer can perform streaming edits."""
        return self._supports_editing
    
    async def start_streaming(self, emitter: "StreamEventEmitter", placeholder_message_id: str) -> None:
        """
        Start consuming stream events and editing the placeholder message.
        
        Args:
            emitter: The agent's stream emitter to subscribe to
            placeholder_message_id: ID of message to progressively edit
        """
        if not self._supports_editing:
            logger.debug("Streaming not supported for %s, falling back to blocking mode", self._platform)
            return
            
        # Capture the current event loop for thread-safe scheduling
        self._event_loop = asyncio.get_running_loop()
        self._emitter = emitter
        self._state = StreamEditState(message_id=placeholder_message_id)
        
        # Subscribe to streaming events
        emitter.add_callback(self._on_stream_event)
        
        logger.debug("Started streaming consumer for %s message %s", 
                    self._platform, placeholder_message_id)
    
    async def finalize(self, final_content: str) -> None:
        """
        Finalize the streaming message with complete content.
        
        Args:
            final_content: The complete final message content
        """
        if not self._state or self._state.is_finalized:
            return
            
        # Cancel any pending edit
        if self._pending_edit_task and not self._pending_edit_task.done():
            self._pending_edit_task.cancel()
            try:
                await self._pending_edit_task
            except asyncio.CancelledError:
                pass
        
        # Ensure final content is edited
        try:
            chunks = self._chunk_message(final_content)
            if chunks:
                await self._edit_message(self._state.message_id, chunks[0])
                
                # Send overflow as new messages if needed
                for chunk in chunks[1:]:
                    await self._send_message(chunk)
                    
        except Exception as e:
            logger.warning("Failed to finalize streaming message: %s", e)
        
        self._state.is_finalized = True
        
        # Unsubscribe from events
        if self._emitter:
            self._emitter.remove_callback(self._on_stream_event)
            
        logger.debug("Finalized streaming message with %d edits", 
                    self._state.total_edits if self._state else 0)
    
    def _on_stream_event(self, event: "StreamEvent") -> None:
        """Handle incoming stream events (sync callback from agent thread)."""
        if not self._state or self._state.is_finalized or not self._event_loop:
            return
            
        # Import here to avoid circular imports
        try:
            from praisonaiagents.streaming.events import StreamEventType
        except ImportError:
            logger.warning("StreamEventType not available, skipping event")
            return
        
        # Only process text deltas
        if event.type == StreamEventType.DELTA_TEXT and event.content:
            self._state.accumulated_content += event.content
            
            # Schedule edit if enough time has passed
            current_time = time.time() * 1000  # Convert to milliseconds
            time_since_last_edit = current_time - self._state.last_edit_time
            
            if time_since_last_edit >= self._edit_interval_ms:
                # Schedule async edit from worker thread using thread-safe scheduling
                try:
                    self._event_loop.call_soon_threadsafe(
                        self._schedule_edit_task
                    )
                except Exception as e:
                    logger.debug("Failed to schedule edit from worker thread: %s", e)
    
    def _schedule_edit_task(self) -> None:
        """Schedule a new edit task (called from event loop thread)."""
        if not self._state or self._state.is_finalized:
            return
            
        # Cancel any existing pending edit
        if self._pending_edit_task and not self._pending_edit_task.done():
            self._pending_edit_task.cancel()
            
        # Create new edit task
        self._pending_edit_task = asyncio.create_task(self._perform_edit())
    
    async def _perform_edit(self) -> None:
        """Perform the actual message edit with accumulated content."""
        if not self._state or self._state.is_finalized:
            return
            
        try:
            # Direct await instead of nested task creation
            await self._edit_with_content()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Stream edit failed: %s", e)
    
    async def _edit_with_content(self) -> None:
        """Edit the message with current accumulated content."""
        if not self._state:
            return
            
        content = self._state.accumulated_content.strip()
        if not content:
            return
            
        # Apply markdown-safe partial rendering
        safe_content = self._make_partial_safe(content)
        
        # Chunk if needed
        chunks = self._chunk_message(safe_content)
        if not chunks:
            return
            
        try:
            # Edit the main message
            await self._edit_message(self._state.message_id, chunks[0])
            self._state.last_edit_time = time.time() * 1000
            self._state.total_edits += 1
            
            # Send overflow as new messages
            for chunk in chunks[1:]:
                await self._send_message(chunk)
                
        except Exception as e:
            # Don't let edit failures stop streaming
            logger.debug("Edit failed (non-fatal): %s", e)
    
    def _make_partial_safe(self, content: str) -> str:
        """
        Make partial content safe for markdown rendering.
        
        Closes open code fences and ensures partial content doesn't
        break markdown formatting.
        """
        # Count unclosed code fences
        fence_count = content.count('```')
        if fence_count % 2 == 1:
            # Odd number means we have an unclosed fence
            content += '\n```'
            
        # Similar logic could be added for other markdown constructs
        # (lists, tables, etc.) if needed
        
        return content
    
    def _chunk_message(self, content: str) -> list[str]:
        """Chunk content to respect platform message limits."""
        if len(content) <= self._max_message_length:
            return [content]
            
        # Use existing chunking utility
        try:
            from ._chunk import chunk_message
            return chunk_message(content, max_length=self._max_message_length, preserve_fences=True)
        except ImportError:
            # Fallback chunking
            chunks = []
            for i in range(0, len(content), self._max_message_length):
                chunks.append(content[i:i + self._max_message_length])
            return chunks
    
    async def _edit_message(self, message_id: str, content: str) -> None:
        """Edit a message via the bot adapter."""
        await self._adapter.edit_message(self._channel_id, message_id, content)
    
    async def _send_message(self, content: str) -> None:
        """Send a new message via the bot adapter."""
        if hasattr(self._adapter, 'send_message'):
            await self._adapter.send_message(self._channel_id, content)
        else:
            logger.warning("Adapter does not support send_message, overflow content lost")


def create_stream_consumer(
    adapter: Any,
    channel_id: str,
    *,
    config: Optional[Dict[str, Any]] = None,
    platform: str = "unknown",
) -> ChannelStreamConsumer:
    """
    Factory function to create a stream consumer with platform-specific config.
    
    Args:
        adapter: Bot adapter instance
        channel_id: Platform channel/chat ID
        config: Optional configuration dict (from BotConfig)
        platform: Platform name
        
    Returns:
        Configured ChannelStreamConsumer instance
    """
    if config is None:
        config = {}
        
    return ChannelStreamConsumer(
        adapter=adapter,
        channel_id=channel_id,
        edit_interval_ms=config.get('stream_edit_interval_ms', 700),
        max_message_length=config.get('max_message_length', 4096),
        platform=platform,
    )