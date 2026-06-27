"""
Streaming response helpers for bot channels.

Provides live draft/streaming reply functionality that connects core SDK streaming
events to bot channel message edits, enabling progressive response delivery.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents.streaming.events import StreamEvent

logger = logging.getLogger(__name__)


# Matches <think>...</think> and <reasoning>...</reasoning> spans (case-insensitive,
# spanning newlines). Also strips a trailing unclosed opening tag so partial
# reasoning never leaks while a block is still streaming.
_REASONING_TAG_RE = re.compile(
    r"<(?:think|reasoning)\b[^>]*>.*?</(?:think|reasoning)>",
    re.IGNORECASE | re.DOTALL,
)
_REASONING_OPEN_RE = re.compile(
    r"<(?:think|reasoning)\b[^>]*>.*\Z",
    re.IGNORECASE | re.DOTALL,
)


def strip_reasoning_tags(text: str) -> str:
    """Remove ``<think>``/``<reasoning>`` spans from streamed content.

    Complete blocks are removed entirely. A trailing *unclosed* opening tag
    (still being streamed) is also dropped so internal reasoning is never
    surfaced mid-stream.

    Args:
        text: Raw buffered content.

    Returns:
        Content with reasoning spans removed.
    """
    if not text:
        return text
    cleaned = _REASONING_TAG_RE.sub("", text)
    cleaned = _REASONING_OPEN_RE.sub("", cleaned)
    return cleaned


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
    # Flood-control / resilience for progressive edits
    disable_progressive_edits_after: int = 3  # Consecutive edit failures before giving up
    flood_backoff_factor: float = 2.0         # Multiply interval on each flood/429
    max_interval: float = 30.0                # Cap for the adaptively-widened interval
    strip_reasoning_tags: bool = True         # Strip <think>/<reasoning> from output
    
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
            disable_progressive_edits_after=data.get("disable_progressive_edits_after", 3),
            flood_backoff_factor=data.get("flood_backoff_factor", 2.0),
            max_interval=data.get("max_interval", 30.0),
            strip_reasoning_tags=data.get("strip_reasoning_tags", True),
        )


class BotAdapter(Protocol):
    """Protocol for bot adapters that support message editing."""
    
    @property
    def capabilities(self) -> Any:
        """Get channel capabilities."""
        ...
    
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
        platform: str = "",
    ):
        self._adapter = adapter
        self._channel_id = channel_id
        self._config = config
        self._rate_limiter = rate_limiter
        self._platform = platform
        
        # State
        self._message_id: Optional[str] = None
        self._content_buffer = ""
        self._last_edit_time = 0.0
        self._last_content_length = 0
        self._current_tool: Optional[str] = None
        self._is_finalized = False
        self._update_task: Optional[asyncio.Task] = None
        self._pending_update = False
        
        # Flood-control state for progressive edits
        self._fail_streak = 0
        self._progressive = True  # When False, fall back to a single final send
        
        # Check capabilities and degrade gracefully
        caps = getattr(adapter, 'capabilities', {})
        self._can_edit = caps.get('live_edit', True)  # Assume true for backward compat
        self._text_limit = caps.get('text_limit', 0) or 0  # 0 = unlimited
        self._edit_rate_limit = caps.get('edit_rate_limit', 0) or 0
        
        # Per-stream runtime interval. Adaptive backoff mutates this, NOT the
        # shared config, so a flood in one stream never leaks into others.
        self._current_min_interval = self._config.min_interval
        
        # Use the more restrictive rate limit between channel capability and config
        if self._edit_rate_limit > 0:
            self._current_min_interval = max(self._current_min_interval, self._edit_rate_limit)
        
        # Override config if channel doesn't support editing
        if not self._can_edit and self._config.mode != StreamingMode.OFF:
            logger.info(
                "Channel %s doesn't support live editing, disabling streaming",
                channel_id
            )
            self._config = StreamingConfig(mode=StreamingMode.OFF)
        
        logger.debug(
            "DraftStreamer initialized for channel %s, mode=%s, can_edit=%s, min_interval=%s",
            channel_id, self._config.mode, self._can_edit, self._current_min_interval
        )
    
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
        if not self._progressive:
            return  # Progressive edits disabled after repeated flood failures
        if self._pending_update:
            return  # Update already scheduled
            
        now = time.monotonic()
        elapsed = now - self._last_edit_time
        content_delta = len(self._content_buffer) - self._last_content_length
        
        # Check if we should update based on time and content thresholds
        should_update = (
            elapsed >= self._current_min_interval and
            content_delta >= self._config.min_delta
        ) or (
            # Always update for progress mode when tool changes
            self._config.mode == StreamingMode.PROGRESS and self._current_tool
        )
        
        if not should_update:
            return
        
        self._pending_update = True
        
        # Calculate delay to respect min_interval
        delay = max(0, self._current_min_interval - elapsed)
        
        # Schedule update as background task to avoid blocking token stream
        async def _delayed_update():
            if delay > 0:
                await asyncio.sleep(delay)
            await self._perform_update()
            self._pending_update = False
        
        # Cancel existing update task if any
        if self._update_task and not self._update_task.done():
            self._update_task.cancel()
        
        # Schedule new update task
        self._update_task = asyncio.create_task(_delayed_update())
    
    def _render_content(self) -> Optional[str]:
        """Render the buffer for the current mode, applying reasoning stripping."""
        buffer = self._content_buffer
        if buffer and self._config.strip_reasoning_tags:
            buffer = strip_reasoning_tags(buffer)
        
        # Prepare content based on mode
        if self._config.mode == StreamingMode.DRAFT:
            content = buffer or self._config.placeholder_text
        elif self._config.mode == StreamingMode.PROGRESS:
            if self._current_tool:
                content = f"{self._config.progress_prefix}Running {self._current_tool}..."
            elif buffer:
                content = buffer
            else:
                content = self._config.placeholder_text
        else:
            return None  # Should not happen
        
        # Apply text limit if configured
        if self._text_limit > 0 and len(content) > self._text_limit:
            content = content[:self._text_limit - 3] + "..."
        
        return content
    
    async def _perform_update(self) -> None:
        """Perform the actual message edit with flood-control handling."""
        if not self._message_id or self._is_finalized or not self._progressive:
            return
        
        content = self._render_content()
        if content is None:
            return
        
        try:
            # Apply rate limiting
            if self._rate_limiter:
                await self._rate_limiter.acquire(self._channel_id)
            
            # Perform edit
            await self._adapter.edit_message(self._channel_id, self._message_id, content)
            
            # Success - reset failure streak and update state
            self._fail_streak = 0
            self._last_edit_time = time.monotonic()
            self._last_content_length = len(self._content_buffer)
            
            logger.debug(
                "DraftStreamer updated message %s, content_length=%d", 
                self._message_id, len(content)
            )
            
        except Exception as e:  # noqa: BLE001 - adapter boundary; classify & back off
            self._handle_edit_failure(e)
    
    def _handle_edit_failure(self, err: Exception) -> None:
        """Adaptively back off on recoverable edit failures.
        
        On flood/429/transient errors, widen the edit interval (capped) and
        track consecutive failures. After ``disable_progressive_edits_after``
        strikes, stop progressive editing so ``finalize`` delivers the full
        answer as a single final send.
        """
        from praisonai.bots._resilience import is_recoverable_error
        
        # Mark the time so we don't immediately retry-flood
        self._last_edit_time = time.monotonic()
        
        if is_recoverable_error(err, self._platform):
            self._fail_streak += 1
            self._current_min_interval = min(
                self._current_min_interval * self._config.flood_backoff_factor,
                self._config.max_interval,
            )
            logger.warning(
                "DraftStreamer edit flood (streak=%d), widening interval to %.1fs: %s",
                self._fail_streak, self._current_min_interval, err,
            )
            if self._fail_streak >= self._config.disable_progressive_edits_after:
                self._progressive = False
                logger.info(
                    "DraftStreamer disabling progressive edits after %d failures; "
                    "falling back to final send only",
                    self._fail_streak,
                )
        else:
            logger.warning("DraftStreamer update failed (non-recoverable): %s", err)
    
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
        
        # Strip reasoning tags from the final answer too
        if final_content and self._config.strip_reasoning_tags:
            final_content = strip_reasoning_tags(final_content)
        
        if self._rate_limiter:
            await self._rate_limiter.acquire(self._channel_id)
        
        # Primary delivery: when progressive edits are still healthy, edit the
        # existing placeholder in place. When they were disabled by flooding, a
        # fresh edit is likely to fail too, so try the placeholder edit first
        # (to avoid leaving a stale "🤔 Thinking..." draft) and fall back to a
        # new send below.
        delivered = False
        try:
            await self._adapter.edit_message(self._channel_id, self._message_id, final_content)
            delivered = True
        except Exception as e:  # noqa: BLE001 - adapter boundary; preserve final delivery
            logger.warning("DraftStreamer final edit failed: %s", e)
        
        # Fallback: if the edit failed (or progressive editing was disabled by
        # flooding), deliver the full answer as a fresh send so the user ALWAYS
        # receives the completed answer regardless of the progressive path taken.
        if not delivered:
            try:
                await self._adapter.send_message(self._channel_id, final_content)
                delivered = True
            except Exception as send_exc:  # noqa: BLE001 - last-resort delivery fallback
                logger.warning(
                    "DraftStreamer final send fallback also failed: %s", send_exc
                )
        
        logger.debug(
            "DraftStreamer finalized message %s, final_length=%d, progressive=%s, delivered=%s",
            self._message_id, len(final_content), self._progressive, delivered
        )
    
    @property
    def is_streaming(self) -> bool:
        """Check if streaming is active."""
        return bool(self._message_id and not self._is_finalized)
    
    @property
    def has_content(self) -> bool:
        """Check if any content has been collected."""
        return bool(self._content_buffer.strip())