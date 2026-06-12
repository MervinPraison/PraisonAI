"""
Streaming response helpers for bot channels.

Provides live draft/streaming reply functionality that connects core SDK streaming
events to bot channel message edits, enabling progressive response delivery.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents.streaming.events import StreamEvent

logger = logging.getLogger(__name__)


class StreamingMode(Enum):
    """Streaming reply modes for bot channels."""
    
    OFF = "off"           # Current behavior (single final message, chunked)
    DRAFT = "draft"       # Send placeholder, edit in place with growing content
    PROGRESS = "progress" # Show compact status, then replace with final answer


@dataclass
class StreamingConfig:
    """Configuration for streaming bot replies."""
    
    mode: StreamingMode = StreamingMode.OFF
    min_interval: float = 1.5      # Minimum seconds between edits
    min_delta: int = 120           # Minimum characters before triggering edit
    placeholder_text: str = "🤔 Thinking..."
    progress_prefix: str = "🤔 "
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StreamingConfig":
        """Create config from dictionary (e.g., from YAML)."""
        mode_str = data.get("mode", "off")
        try:
            mode = StreamingMode(mode_str)
        except ValueError:
            logger.warning("Invalid streaming mode '%s', using 'off'", mode_str)
            mode = StreamingMode.OFF
        
        return cls(
            mode=mode,
            min_interval=data.get("min_interval", 1.5),
            min_delta=data.get("min_delta", 120),
            placeholder_text=data.get("placeholder_text", "🤔 Thinking..."),
            progress_prefix=data.get("progress_prefix", "🤔 "),
        )


class BotAdapter(Protocol):
    """Protocol for bot adapters that support message editing."""
    
    async def send_message(self, channel_id: str, content: str) -> Any:
        """Send a new message and return message info."""
        ...
    
    async def edit_message(self, channel_id: str, message_id: str, content: str) -> Any:
        """Edit an existing message."""
        ...


class DraftStreamer:
    """
    Manages live draft updates for streaming bot replies.
    
    Subscribes to agent streaming events and progressively updates a bot message
    with growing content, respecting rate limits and coalescing updates.
    
    Usage:
        streamer = DraftStreamer(
            adapter=bot_adapter,
            channel_id="123456",
            config=StreamingConfig(mode=StreamingMode.DRAFT, min_interval=1.5)
        )
        
        # Start streaming
        message_id = await streamer.start()
        
        # Subscribe to agent events
        response = await agent.chat(
            prompt,
            stream_callback=streamer.on_event
        )
        
        # Finalize with complete response  
        await streamer.finalize(response)
    """
    
    def __init__(
        self,
        adapter: BotAdapter,
        channel_id: str,
        config: StreamingConfig,
        rate_limiter: Optional[Any] = None,
    ):
        self._adapter = adapter
        self._channel_id = channel_id
        self._config = config
        self._rate_limiter = rate_limiter
        
        # State
        self._message_id: Optional[str] = None
        self._content_buffer = ""
        self._last_edit_time = 0.0
        self._last_content_length = 0
        self._current_tool: Optional[str] = None
        self._is_finalized = False
        self._update_task: Optional[asyncio.Task] = None
        self._pending_update = False
        
        logger.debug("DraftStreamer initialized for channel %s, mode=%s", channel_id, config.mode)
    
    async def start(self) -> str:
        """Start streaming by sending initial placeholder message.
        
        Returns:
            Message ID of the placeholder message
        """
        if self._config.mode == StreamingMode.OFF:
            raise ValueError("Cannot start streaming when mode is OFF")
        
        if self._rate_limiter:
            await self._rate_limiter.acquire(self._channel_id)
        
        # Send placeholder
        placeholder = self._config.placeholder_text
        message_info = await self._adapter.send_message(self._channel_id, placeholder)
        
        # Extract message ID - adapt to different bot adapter formats
        if hasattr(message_info, 'message_id'):
            self._message_id = message_info.message_id
        elif isinstance(message_info, dict) and 'message_id' in message_info:
            self._message_id = message_info['message_id']
        elif hasattr(message_info, 'id'):
            self._message_id = str(message_info.id)
        else:
            # Fallback - try to extract from string representation
            self._message_id = str(message_info)
        
        self._last_edit_time = time.monotonic()
        logger.debug("DraftStreamer started, placeholder sent with message_id=%s", self._message_id)
        return self._message_id
    
    async def on_event(self, event: "StreamEvent") -> None:
        """Stream event callback to handle progressive updates."""
        if self._is_finalized or not self._message_id:
            return
        
        # Import here to avoid circular imports
        from praisonaiagents.streaming.events import StreamEventType
        
        if event.type == StreamEventType.DELTA_TEXT and event.content:
            self._content_buffer += event.content
            await self._schedule_update()
            
        elif event.type == StreamEventType.DELTA_TOOL_CALL and event.tool_call:
            tool_name = event.tool_call.get('name', 'unknown_tool')
            if self._config.mode == StreamingMode.PROGRESS:
                # Update current tool for progress display
                self._current_tool = tool_name
                await self._schedule_update()
            
        elif event.type == StreamEventType.TOOL_CALL_START and event.tool_call:
            tool_name = event.tool_call.get('name', 'unknown_tool')
            if self._config.mode == StreamingMode.PROGRESS:
                self._current_tool = tool_name
                await self._schedule_update()
                
        elif event.type == StreamEventType.STREAM_END:
            # Final update will be handled by finalize()
            pass
    
    async def _schedule_update(self) -> None:
        """Schedule a throttled update if conditions are met."""
        if self._pending_update:
            return  # Update already scheduled
            
        now = time.monotonic()
        elapsed = now - self._last_edit_time
        content_delta = len(self._content_buffer) - self._last_content_length
        
        # Check if we should update based on time and content thresholds
        should_update = (
            elapsed >= self._config.min_interval and
            content_delta >= self._config.min_delta
        ) or (
            # Always update for progress mode when tool changes
            self._config.mode == StreamingMode.PROGRESS and self._current_tool
        )
        
        if not should_update:
            return
        
        self._pending_update = True
        
        # Calculate delay to respect min_interval
        delay = max(0, self._config.min_interval - elapsed)
        
        if delay > 0:
            await asyncio.sleep(delay)
        
        await self._perform_update()
        self._pending_update = False
    
    async def _perform_update(self) -> None:
        """Perform the actual message edit."""
        if not self._message_id or self._is_finalized:
            return
        
        try:
            # Apply rate limiting
            if self._rate_limiter:
                await self._rate_limiter.acquire(self._channel_id)
            
            # Prepare content based on mode
            if self._config.mode == StreamingMode.DRAFT:
                content = self._content_buffer or self._config.placeholder_text
            elif self._config.mode == StreamingMode.PROGRESS:
                if self._current_tool:
                    content = f"{self._config.progress_prefix}Running {self._current_tool}..."
                elif self._content_buffer:
                    content = self._content_buffer
                else:
                    content = self._config.placeholder_text
            else:
                return  # Should not happen
            
            # Perform edit
            await self._adapter.edit_message(self._channel_id, self._message_id, content)
            
            # Update state
            self._last_edit_time = time.monotonic()
            self._last_content_length = len(self._content_buffer)
            
            logger.debug(
                "DraftStreamer updated message %s, content_length=%d", 
                self._message_id, len(content)
            )
            
        except Exception as e:
            logger.warning("DraftStreamer update failed: %s", e)
    
    async def finalize(self, final_content: str) -> None:
        """Finalize with the complete response content."""
        if self._is_finalized or not self._message_id:
            return
        
        self._is_finalized = True
        
        # Cancel any pending updates
        if self._update_task and not self._update_task.done():
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        
        try:
            # Apply rate limiting
            if self._rate_limiter:
                await self._rate_limiter.acquire(self._channel_id)
            
            # Final edit with complete content
            await self._adapter.edit_message(self._channel_id, self._message_id, final_content)
            
            logger.debug(
                "DraftStreamer finalized message %s, final_length=%d", 
                self._message_id, len(final_content)
            )
            
        except Exception as e:
            logger.warning("DraftStreamer finalization failed: %s", e)
    
    @property
    def is_streaming(self) -> bool:
        """Check if streaming is active."""
        return bool(self._message_id and not self._is_finalized)
    
    @property
    def has_content(self) -> bool:
        """Check if any content has been collected."""
        return bool(self._content_buffer.strip())