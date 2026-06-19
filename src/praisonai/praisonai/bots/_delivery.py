"""
Unified and durable message delivery for PraisonAI bots.

Provides both unified delivery with platform capabilities (streaming, chunking,
rate limiting) and durable delivery with persistence and retry logic.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional, Union, Dict, Any, List, Awaitable, Callable, Protocol

if TYPE_CHECKING:
    from praisonaiagents.bots import BotProtocol, PlatformCapabilities

from ._chunk import chunk_message, _calculate_length
from ._streaming import DraftStreamer, StreamingConfig, StreamingMode
from ._rate_limit import RateLimiter
from ._resilience import BackoffPolicy, compute_backoff, is_recoverable_error, sleep_with_abort

logger = logging.getLogger(__name__)


class MessageSender(Protocol):
    """Protocol for message sending implementations."""
    
    async def send_message(
        self,
        channel_id: str,
        content: Union[str, Dict[str, Any]],
        **kwargs
    ) -> Any:
        """Send a message to a channel."""
        ...


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


async def deliver_with_retry(
    adapter: MessageSender,
    channel_id: str,
    content: Union[str, Dict[str, Any]],
    *,
    backoff: Optional[BackoffPolicy] = None,
    max_attempts: int = 3,
    abort_signal: Optional[asyncio.Event] = None,
    platform: str = "",
    **send_kwargs
) -> tuple[bool, Optional[str]]:
    """Attempt delivery with bounded exponential backoff retry.
    
    Args:
        adapter: The adapter to send through
        channel_id: Target channel ID
        content: Message content to send
        backoff: Backoff policy for retries
        max_attempts: Maximum delivery attempts
        abort_signal: Optional event to cancel retries
        platform: Platform name for error classification
        **send_kwargs: Additional kwargs for send_message
        
    Returns:
        Tuple of (success, error_message)
        - (True, None) on successful delivery
        - (False, error_msg) on permanent failure
        - (False, error_msg) on transient failure after max attempts
    """
    backoff = backoff or BackoffPolicy()
    last_error = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            # Attempt delivery
            await adapter.send_message(channel_id, content, **send_kwargs)
            
            # Success!
            if attempt > 1:
                logger.info(
                    f"[{platform}] Delivery succeeded after {attempt} attempts "
                    f"to channel {channel_id}"
                )
            
            return True, None
            
        except Exception as e:
            last_error = str(e)
            
            # Check if error is permanent
            if not is_recoverable_error(e, platform):
                logger.error(
                    f"[{platform}] Permanent delivery failure to {channel_id}: {e}"
                )
                return False, f"Permanent error: {last_error}"
            
            # Check if we're out of attempts
            if attempt >= max_attempts:
                logger.warning(
                    f"[{platform}] Delivery failed after {attempt} attempts "
                    f"to {channel_id}: {e}"
                )
                return False, f"Max attempts exceeded: {last_error}"
            
            # Calculate backoff delay
            delay = compute_backoff(backoff, attempt)
            
            logger.warning(
                f"[{platform}] Delivery attempt {attempt} failed to {channel_id}: "
                f"{e}; retrying in {delay:.1f}s"
            )
            
            # Sleep with abort capability
            if not await sleep_with_abort(delay, abort_signal):
                logger.info(f"[{platform}] Delivery retry aborted by signal")
                return False, "Aborted by signal"
    
    # Should never reach here, but for safety
    return False, last_error


async def deliver_chunked(
    adapter: MessageSender,
    channel_id: str,
    content: str,
    *,
    max_length: int = 4096,
    preserve_fences: bool = True,
    **send_kwargs
) -> int:
    """Deliver a long message in chunks.
    
    Args:
        adapter: The adapter to send through
        channel_id: Target channel ID  
        content: Message content to send
        max_length: Maximum length per chunk
        preserve_fences: Whether to preserve code fence boundaries
        **send_kwargs: Additional kwargs for send_message
        
    Returns:
        Number of chunks sent
    """
    if len(content) <= max_length:
        await adapter.send_message(channel_id, content, **send_kwargs)
        return 1
    
    chunks = chunk_message(content, max_length=max_length, preserve_fences=preserve_fences)
    
    for i, chunk in enumerate(chunks):
        # Only apply reply_to to first chunk
        chunk_kwargs = send_kwargs.copy()
        if i > 0 and 'reply_to' in chunk_kwargs:
            chunk_kwargs.pop('reply_to')
        
        await adapter.send_message(channel_id, chunk, **chunk_kwargs)
    
    return len(chunks)


class DurableDelivery:
    """Helper for durable message delivery with outbound queue integration.
    
    Example::
    
        from praisonai.bots import OutboundQueue, DurableDelivery, TelegramAdapter
        
        outbox = OutboundQueue(path="~/.praisonai/state/outbox.sqlite")
        adapter = TelegramAdapter(token="...")
        delivery = DurableDelivery(outbox, adapter, platform="telegram")
        
        # Send with durability
        success = await delivery.send(
            channel_id="12345",
            content="Hello, world!",
            idempotency_key="msg-123"
        )
        
        # On startup, drain pending
        await delivery.drain_pending()
    """
    
    def __init__(
        self,
        outbox: Optional[Any] = None,  # OutboundQueue
        adapter: Optional[MessageSender] = None,
        *,
        platform: str = "",
        backoff: Optional[BackoffPolicy] = None,
        max_attempts: int = 3,
    ):
        self.outbox = outbox
        self.adapter = adapter
        self.platform = platform
        self.backoff = backoff or BackoffPolicy()
        self.max_attempts = max_attempts
    
    async def send(
        self,
        channel_id: str,
        content: Union[str, Dict[str, Any]],
        *,
        idempotency_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **send_kwargs
    ) -> bool:
        """Send a message with optional durability.
        
        If outbox is configured, the message is persisted before sending
        and marked as sent only on success. On failure, it remains in the
        queue for later retry via drain_pending().
        
        Args:
            channel_id: Target channel ID
            content: Message content
            idempotency_key: Optional key for deduplication
            metadata: Optional metadata for tracking
            **send_kwargs: Additional kwargs for send_message
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.adapter:
            raise RuntimeError("No adapter configured")
        
        # If no outbox, just send directly with retry
        if not self.outbox:
            success, _ = await deliver_with_retry(
                self.adapter,
                channel_id,
                content,
                backoff=self.backoff,
                max_attempts=self.max_attempts,
                platform=self.platform,
                **send_kwargs
            )
            return success
        
        # With outbox: persist first, then deliver
        if not idempotency_key:
            import uuid
            idempotency_key = str(uuid.uuid4())
        
        # Prepare payload
        payload = {
            "content": content,
            "kwargs": send_kwargs,
        }
        
        # Enqueue
        target = f"{self.platform}:{channel_id}" if self.platform else channel_id
        key = await self.outbox.enqueue(
            idempotency_key=idempotency_key,
            target=target,
            payload=payload,
            metadata=metadata,
        )
        
        # Attempt delivery
        success, error = await deliver_with_retry(
            self.adapter,
            channel_id,
            content,
            backoff=self.backoff,
            max_attempts=self.max_attempts,
            platform=self.platform,
            **send_kwargs
        )
        
        # Update status
        if success:
            await self.outbox.mark_sent(key)
        else:
            # Check if permanent error
            permanent = error and "Permanent error:" in error
            await self.outbox.mark_failed(key, error or "Unknown error", permanent=permanent)
        
        return success
    
    async def drain_pending(self, limit: Optional[int] = None) -> tuple[int, int]:
        """Process pending messages from the outbox.
        
        Called on startup to retry messages that failed to send.
        
        Args:
            limit: Optional max messages to process
            
        Returns:
            Tuple of (succeeded, failed) counts
        """
        if not self.outbox:
            return 0, 0
        
        if not self.adapter:
            raise RuntimeError("No adapter configured")
        
        async def sender(target: str, payload: Dict[str, Any]) -> bool:
            """Delivery function for outbox.drain()"""
            # Extract channel_id from target
            if ":" in target:
                _, channel_id = target.split(":", 1)
            else:
                channel_id = target
            
            # Extract content and kwargs
            content = payload.get("content", "")
            send_kwargs = payload.get("kwargs", {})
            
            # Attempt delivery with retry
            success, error = await deliver_with_retry(
                self.adapter,
                channel_id,
                content,
                backoff=self.backoff,
                max_attempts=1,  # Single attempt per drain cycle
                platform=self.platform,
                **send_kwargs
            )
            
            # Preserve permanent failure information
            if not success and error and error.startswith("Permanent error:"):
                raise RuntimeError(error)
            
            return success
        
        return await self.outbox.drain(sender, limit=limit)


__all__ = [
    "UnifiedDelivery",
    "create_delivery",
    "MessageSender",
    "deliver_with_retry", 
    "deliver_chunked",
    "DurableDelivery",
]