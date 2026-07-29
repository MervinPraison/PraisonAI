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
  - Safe by default (Issue #3446): symmetric with the inbound journal, which is
    durable-by-default, the outbound reply — the most expensive artifact of the
    turn — is a durable delivery obligation by default. When no ``dlq_path`` is
    configured a canonical per-platform DLQ under
    ``~/.praisonai/state/<platform>/`` is used automatically, so a permanent or
    exhausted send failure is *parked* (auditable + replayable) instead of
    silently dropped. Operators opt out explicitly with
    ``outbound_resilience.enabled = false``.
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
    error is permanent, the reply is enqueued in the adapter's outbound DLQ so
    it can be replayed, and the original exception is re-raised so callers keep
    their existing error semantics. The DLQ is on by default at a canonical
    per-platform path (Issue #3446); ``outbound_resilience.enabled = false``
    opts out.

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
        self._outbound_backoff: BackoffPolicy = BackoffPolicy(**_DEFAULT_BACKOFF)
        self._outbound_dlq: Optional[Any] = None

        config = getattr(self, "config", None)
        outbound_resilience = getattr(config, "outbound_resilience", None) if config else None

        if outbound_resilience is not None and not getattr(outbound_resilience, "enabled", True):
            # Operator explicitly opted this channel out of the durable path.
            self._outbound_backoff = BackoffPolicy(initial_ms=1000, max_ms=10000, factor=1.5, max_attempts=1)
            self._outbound_resilience_ready = True
            return

        if outbound_resilience is not None:
            self._outbound_backoff = BackoffPolicy(
                initial_ms=getattr(outbound_resilience, "initial_ms", 1000),
                max_ms=getattr(outbound_resilience, "max_ms", 10000),
                factor=getattr(outbound_resilience, "factor", 1.5),
                max_attempts=getattr(outbound_resilience, "max_attempts", 3),
                jitter=getattr(outbound_resilience, "jitter", 0.25),
            )

        # Safe-by-default outbound park (Issue #3446): honour an explicit
        # ``dlq_path`` when given, otherwise fall back to the canonical
        # per-platform store used by the inbound journal so a permanently
        # failed / exhausted reply is parked by default rather than lost. The
        # operator escape hatch is ``outbound_resilience.enabled = false``,
        # handled above (returns before this point).
        dlq_path = getattr(outbound_resilience, "dlq_path", None) if outbound_resilience is not None else None
        if not dlq_path:
            dlq_path = self._default_outbound_dlq_path()
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
                # Storage may be transiently unavailable. Degrade this send to
                # retry-only but do NOT latch ``_outbound_resilience_ready`` so a
                # later delivery re-attempts DLQ init once storage recovers,
                # rather than permanently disabling durable parking.
                logger.warning(
                    "Failed to initialize outbound DLQ (will retry on next send): %s", e
                )
                return

        self._outbound_resilience_ready = True

    def _default_outbound_dlq_path(self) -> Optional[str]:
        """Canonical default DLQ path, mirroring the inbound journal default.

        Returns ``~/.praisonai/state/<platform>/outbound_dlq.sqlite`` (created
        on use) so the agent's reply is a durable delivery obligation by
        default without any configuration. Returns ``None`` if the store dir
        cannot be resolved, in which case the adapter degrades to retry-only.
        """
        try:
            from ._session import resolve_durable_store_dir

            store_dir = resolve_durable_store_dir(self._outbound_platform or "")
            return str(store_dir / "outbound_dlq.sqlite")
        except Exception as e:  # pragma: no cover — defensive
            logger.warning("Could not resolve default outbound DLQ path: %s", e)
            return None

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
