"""
Durable adapter mixin for PraisonAI bot adapters.

Provides a base implementation for adapters that want to use
durable outbound delivery.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Literal, Optional, Union

from ._delivery import DurableDelivery
from ._outbox import OutboundQueue

logger = logging.getLogger(__name__)


class DurableAdapterMixin:
    """Mixin for bot adapters to add durable outbound delivery.
    
    Usage::
    
        class MyAdapter(DurableAdapterMixin, BaseAdapter):
            def __init__(self, ..., outbox_path: Optional[str] = None):
                super().__init__()
                self.setup_durable_delivery(
                    outbox_path=outbox_path,
                    platform="myplatform"
                )
            
            async def send_message(self, channel_id: str, content: str) -> Any:
                # Use durable send if configured
                if self.durable_delivery:
                    success = await self.durable_delivery.send(
                        channel_id=channel_id,
                        content=content,
                        idempotency_key=f"msg-{channel_id}-{time.time()}"
                    )
                    if not success:
                        raise Exception("Failed to send message")
                    return {"success": True}
                
                # Fallback to direct send
                return await self._raw_send(channel_id, content)
            
            async def _raw_send(self, channel_id: str, content: str) -> Any:
                # Actual platform-specific send logic
                ...
            
            async def start(self):
                # Drain pending messages on startup
                if self.durable_delivery:
                    succeeded, failed = await self.durable_delivery.drain_pending()
                    if succeeded or failed:
                        logger.info(
                            f"Drained outbox: {succeeded} sent, {failed} failed"
                        )
    """
    
    def setup_durable_delivery(
        self,
        outbox_path: Optional[str] = None,
        platform: str = "",
        max_attempts: int = 3,
        max_size: int = 50_000,
        ttl_seconds: int = 7 * 86400,
        ordering: Literal["strict", "best_effort"] = "best_effort",
    ) -> None:
        """Set up durable outbound delivery.
        
        Args:
            outbox_path: Path to SQLite outbox file. If None, durability is disabled.
            platform: Platform name for error classification
            max_attempts: Maximum delivery attempts per message
            max_size: Maximum messages in outbox
            ttl_seconds: TTL for sent messages
            ordering: Per-conversation delivery ordering discipline forwarded to
                :class:`OutboundQueue`. ``"best_effort"`` (default) preserves the
                historic global-order behaviour; ``"strict"`` enforces per-lane
                FIFO so a later same-conversation message can never overtake an
                earlier undelivered one. The ``reliability="production"`` preset
                resolves to ``"strict"`` via ``resolve_reliability``.
        """
        self.outbox: Optional[OutboundQueue] = None
        self.durable_delivery: Optional[DurableDelivery] = None
        
        if outbox_path:
            try:
                self.outbox = OutboundQueue(
                    path=outbox_path,
                    max_size=max_size,
                    ttl_seconds=ttl_seconds,
                    max_attempts=max_attempts,
                    ordering=ordering,
                )
                
                self.durable_delivery = DurableDelivery(
                    outbox=self.outbox,
                    adapter=self,  # Adapter must implement MessageSender protocol
                    platform=platform,
                    max_attempts=max_attempts,
                )
                
                logger.info(
                    f"[{platform}] Durable delivery enabled: {outbox_path} "
                    f"(pending={self.outbox.pending_count()})"
                )
                
            except Exception as e:
                logger.error(f"Failed to set up durable delivery: {e}")
                self.outbox = None
                self.durable_delivery = None
    
    async def drain_outbox(self) -> tuple[int, int]:
        """Drain pending messages from the outbox.
        
        Should be called on adapter startup.
        
        Returns:
            Tuple of (succeeded, failed) counts
        """
        if hasattr(self, 'durable_delivery') and self.durable_delivery:
            return await self.durable_delivery.drain_pending()
        return 0, 0
    
    async def send_durable(
        self,
        channel_id: str,
        content: Union[str, Dict[str, Any]],
        *,
        idempotency_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **send_kwargs
    ) -> bool:
        """Send a message with durable delivery.
        
        If outbox is configured, the message is persisted before sending.
        If not configured, falls back to direct send.
        
        Args:
            channel_id: Target channel ID
            content: Message content
            idempotency_key: Optional deduplication key
            metadata: Optional tracking metadata
            **send_kwargs: Additional kwargs for send_message
            
        Returns:
            True if sent successfully, False otherwise
        """
        if hasattr(self, 'durable_delivery') and self.durable_delivery:
            return await self.durable_delivery.send(
                channel_id=channel_id,
                content=content,
                idempotency_key=idempotency_key,
                metadata=metadata,
                **send_kwargs
            )
        
        # Fallback to direct send if no durability configured
        try:
            await self.send_message(channel_id, content, **send_kwargs)
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False


__all__ = ["DurableAdapterMixin"]