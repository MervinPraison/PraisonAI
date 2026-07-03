"""
Shared outbound-resilience mixin for PraisonAI bot adapters.

The Telegram adapter has long wrapped every outbound send in
``deliver_with_retry`` (bounded exponential backoff that honours a server
``Retry-After``) and parked permanently-failed replies in an ``OutboundDLQ``
for later replay. Slack, Discord, WhatsApp, Email, Linear, and AgentMail used
to send directly, so a transient channel error (HTTP 5xx, rate limit, network
blip) silently dropped the agent's reply with no recovery.

This module extracts that proven Telegram wiring into a reusable mixin so every
adapter delivers through the same durable path **by default**: retry with
backoff, then route to the DLQ on permanent failure / exhausted attempts.

Design constraints (per PraisonAI principles):
  - Wrapper-only — heavy implementation stays out of the core SDK.
  - Lazy: resilience state is built on first send from ``self.config``; no
    ``__init__`` changes are required in the adapters.
  - Optional / backward-compatible: when no ``dlq_path`` is configured the
    adapter behaves exactly as before except that transient errors are now
    retried instead of dropped.
  - Bounded: backoff caps attempts; the DLQ enforces TTL + max_size.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional

from ._resilience import BackoffPolicy, deliver_with_retry

logger = logging.getLogger(__name__)

_DEFAULT_BACKOFF = dict(initial_ms=1000, max_ms=10000, factor=1.5, max_attempts=3, jitter=0.25)


class OutboundResilienceMixin:
    """Add durable outbound delivery (retry/backoff + DLQ park) to an adapter.

    Adapters wrap their raw channel send in :meth:`deliver_outbound`::

        sent = await self.deliver_outbound(
            lambda: self._client.chat_postMessage(channel=cid, text=text),
            channel_id=cid,
            reply_text=text,
            thread_id=thread_id,
            reply_to=reply_to,
        )

    The wrapper retries transient failures with bounded exponential backoff
    (honouring any server ``Retry-After``). When retries are exhausted or the
    error is permanent, the reply is enqueued in the adapter's outbound DLQ (if
    a ``dlq_path`` is configured) so it can be replayed, and the original
    exception is re-raised so callers keep their existing error semantics.

    Resilience state is initialised lazily from ``self.config.outbound_resilience``
    so existing adapter constructors need no changes.
    """

    # Subclasses set this so DLQ entries / logs carry the right platform name.
    _outbound_platform: str = ""

    def _ensure_outbound_resilience(self) -> None:
        """Build backoff policy + optional DLQ once, from ``self.config``.

        Mirrors the Telegram adapter's configuration logic so behaviour is
        consistent across channels. Safe to call repeatedly.
        """
        if getattr(self, "_outbound_resilience_ready", False):
            return
        self._outbound_resilience_ready = True
        self._outbound_backoff: BackoffPolicy = BackoffPolicy(**_DEFAULT_BACKOFF)
        self._outbound_dlq: Optional[Any] = None

        config = getattr(self, "config", None)
        outbound_resilience = getattr(config, "outbound_resilience", None) if config else None

        if outbound_resilience is not None and not getattr(outbound_resilience, "enabled", True):
            # Operator explicitly opted this channel out of the durable path.
            self._outbound_backoff = BackoffPolicy(initial_ms=1000, max_ms=10000, factor=1.5, max_attempts=1)
            return

        if outbound_resilience is not None:
            self._outbound_backoff = BackoffPolicy(
                initial_ms=getattr(outbound_resilience, "initial_ms", 1000),
                max_ms=getattr(outbound_resilience, "max_ms", 10000),
                factor=getattr(outbound_resilience, "factor", 1.5),
                max_attempts=getattr(outbound_resilience, "max_attempts", 3),
                jitter=getattr(outbound_resilience, "jitter", 0.25),
            )
            dlq_path = getattr(outbound_resilience, "dlq_path", None)
            if dlq_path:
                try:
                    from ._dlq import OutboundDLQ

                    self._outbound_dlq = OutboundDLQ(path=dlq_path)
                    logger.info(
                        "[%s] Outbound DLQ initialized at %s",
                        self._outbound_platform or "bot",
                        dlq_path,
                    )
                except Exception as e:  # pragma: no cover — defensive
                    logger.warning("Failed to initialize outbound DLQ: %s", e)

    async def deliver_outbound(
        self,
        send_func: Callable[[], Awaitable[Any]],
        *,
        channel_id: str,
        reply_text: str,
        thread_id: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> Any:
        """Execute ``send_func`` with retry/backoff and DLQ park on failure.

        Args:
            send_func: Zero-arg async callable performing the raw channel send.
            channel_id: Target channel/recipient (for DLQ replay metadata).
            reply_text: The reply text (for DLQ replay metadata).
            thread_id: Optional thread identifier (for DLQ replay metadata).
            reply_to: Optional reply-to identifier (for DLQ replay metadata).

        Returns:
            Whatever ``send_func`` returns on success.

        Raises:
            The original exception if delivery fails permanently or after
            retries are exhausted (after parking it in the DLQ when configured),
            preserving each adapter's existing error-propagation contract.
        """
        self._ensure_outbound_resilience()
        return await deliver_with_retry(
            send_func,
            policy=self._outbound_backoff,
            platform=self._outbound_platform,
            parked_store=self._outbound_dlq,
            reply_data={
                "channel_id": str(channel_id),
                "reply_text": reply_text,
                "thread_id": thread_id or "",
                "reply_to": reply_to or "",
            },
        )


__all__ = ["OutboundResilienceMixin"]
