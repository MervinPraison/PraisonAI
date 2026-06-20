"""
Enhanced ScheduledAgentExecutor with home channel and delivery token support.

Extends the base executor with:
- Home channel registry integration
- Delivery token resolution (origin, platform names, all)
- Standalone sender support for when gateway is not running
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Callable, Optional

# Delivery timeout in seconds
DELIVERY_TIMEOUT_SECONDS = 30

from praisonaiagents.gateway.protocols import (
    DeliveryResolverProtocol,
    HomeChannelRegistryProtocol,
)
from praisonaiagents.scheduler.models import DeliveryTarget

from .executor import ScheduledAgentExecutor, JobResult

if TYPE_CHECKING:
    from praisonaiagents.scheduler import ScheduleRunner, ScheduleJob

logger = logging.getLogger(__name__)


class EnhancedScheduledAgentExecutor(ScheduledAgentExecutor):
    """Enhanced executor with home channel and delivery token support.
    
    Parameters:
        runner: An SDK ``ScheduleRunner`` instance.
        agent_resolver: A callable ``(agent_id: str | None) -> Agent``
            that returns an agent for the given ID.
        delivery_handler: Optional async callable
            ``(delivery: DeliveryTarget, text: str) -> None``.
            Called after successful execution when the job has a
            delivery target.
        home_registry: Optional home channel registry for platform defaults.
        delivery_resolver: Optional delivery token resolver.
        standalone_sender: Optional factory for creating standalone senders
            when the gateway is not running.
        on_success: Optional callback ``(job, result) -> None``.
        on_failure: Optional callback ``(job, error) -> None``.
    """
    
    def __init__(
        self,
        runner: "ScheduleRunner",
        agent_resolver: Callable[[Optional[str]], Any],
        *,
        delivery_handler: Optional[Callable[..., Any]] = None,
        home_registry: Optional[HomeChannelRegistryProtocol] = None,
        delivery_resolver: Optional[DeliveryResolverProtocol] = None,
        standalone_sender: Optional[Callable[[str], Any]] = None,
        on_success: Optional[Callable[..., None]] = None,
        on_failure: Optional[Callable[..., None]] = None,
    ) -> None:
        super().__init__(
            runner=runner,
            agent_resolver=agent_resolver,
            delivery_handler=delivery_handler,
            on_success=on_success,
            on_failure=on_failure,
        )
        self._home_registry = home_registry
        self._delivery_resolver = delivery_resolver
        self._standalone_sender = standalone_sender
    
    async def _execute_one(self, job: "ScheduleJob") -> JobResult:
        """Execute a single scheduled job with enhanced delivery.
        
        Overrides base implementation to add delivery token resolution
        and standalone sender support.
        """
        # Check if we need to skip base delivery
        delivery = getattr(job, "delivery", None)
        deliver_token = getattr(delivery, "deliver", "") if delivery else ""
        
        # If we have a delivery token, temporarily disable base delivery
        # to prevent it from attempting delivery with empty channel/channel_id
        original_deliver = self._deliver
        if deliver_token and delivery:
            # Check if this is a token-only delivery (no explicit channel/channel_id)
            if not delivery.channel or not delivery.channel_id:
                self._deliver = None  # Disable base delivery
        
        # Run the base execution
        result = await super()._execute_one(job)
        
        # Restore original delivery handler
        self._deliver = original_deliver
        
        # If failed or no delivery needed, we're done
        if result.status != "succeeded" or not delivery:
            return result
        
        # If no delivery token, base already handled it
        if not deliver_token:
            return result
        
        # Resolve the delivery token
        if self._delivery_resolver:
            try:
                origin = getattr(job, "origin", None)
                targets = self._delivery_resolver.resolve(
                    deliver_token,
                    origin=origin,
                )
                
                # Deliver to all resolved targets
                delivered_count = 0
                for target in targets:
                    try:
                        # Try primary delivery handler first
                        if self._deliver:
                            coro = self._deliver(target, result.result)
                            if asyncio.iscoroutine(coro):
                                await asyncio.wait_for(coro, timeout=DELIVERY_TIMEOUT_SECONDS)
                            delivered_count += 1
                            logger.info(
                                "Delivered job '%s' via token '%s' to %s:%s",
                                job.id,
                                deliver_token,
                                target.channel,
                                target.channel_id,
                            )
                        # Fall back to standalone sender if no handler
                        elif self._standalone_sender and target.channel:
                            sender = self._standalone_sender(target.channel)
                            if sender:
                                await asyncio.wait_for(
                                    self._send_standalone(
                                        sender,
                                        target,
                                        result.result,
                                    ),
                                    timeout=DELIVERY_TIMEOUT_SECONDS,
                                )
                                delivered_count += 1
                                logger.info(
                                    "Delivered job '%s' via standalone sender to %s:%s",
                                    job.id,
                                    target.channel,
                                    target.channel_id,
                                )
                    except asyncio.TimeoutError:
                        logger.warning(
                            "Delivery timeout for job '%s' to %s:%s after %d seconds",
                            job.id,
                            target.channel,
                            target.channel_id,
                            DELIVERY_TIMEOUT_SECONDS,
                        )
                    except Exception as e:
                        logger.warning(
                            "Delivery failed for job '%s' to %s:%s: %s",
                            job.id,
                            target.channel,
                            target.channel_id,
                            e,
                        )
                
                # Update result with delivery status
                if delivered_count > 0:
                    result.delivered = True
                    logger.info(
                        "Delivered job '%s' to %d targets via token '%s'",
                        job.id,
                        delivered_count,
                        deliver_token,
                    )
                    
                    # Update the job history with correct delivery status
                    # This is necessary because base executor already called mark_run
                    # with delivered=False
                    if hasattr(self._runner, 'mark_run'):
                        self._runner.mark_run(
                            job,
                            status="succeeded",
                            result=result.result,
                            duration=result.duration,
                            delivered=True,
                        )
                    
            except Exception as e:
                logger.error(
                    "Failed to resolve delivery token '%s' for job '%s': %s",
                    deliver_token,
                    job.id,
                    e,
                )
        
        return result
    
    async def _send_standalone(
        self,
        sender: Any,
        target: DeliveryTarget,
        text: str,
    ) -> None:
        """Send via standalone sender when gateway is not running.
        
        Args:
            sender: Platform-specific sender instance
            target: Delivery target with channel info
            text: Message text to send
        """
        # The sender should have a send_message method
        # This is platform-specific
        if hasattr(sender, "send_message"):
            await asyncio.wait_for(
                sender.send_message(
                    chat_id=target.channel_id,
                    text=text,
                    thread_id=target.thread_id,
                ),
                timeout=DELIVERY_TIMEOUT_SECONDS,
            )
        else:
            logger.warning(
                "Standalone sender for %s does not support send_message",
                target.channel,
            )
