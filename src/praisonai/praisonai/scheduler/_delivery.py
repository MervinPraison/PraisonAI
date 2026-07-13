"""Lightweight delivery for interval / scheduled agents.

Wires the wrapper :class:`~praisonai.scheduler.agent_scheduler.AgentScheduler`
``deliver=`` target to the *same* resilient delivery machinery BotOS uses —
without standing up the full gateway. It reuses:

- ``praisonaiagents.scheduler.DeliveryTarget`` — the core, serialisable target
  (parsed from a ``"telegram:123456"`` style token via ``DeliveryTarget.parse``).
- ``praisonai_bot.bots.delivery.DeliveryRouter`` — symbolic-target resolution,
  token-bucket rate limiting, in-process idempotency dedup and dead-target
  skip/self-heal.

So a scheduled result is delivered with the same guarantees as the gateway's
``_deliver_scheduled_result``, but reachable from a few lines of Python / YAML /
CLI. If the optional ``praisonai-bot`` package is not installed the helper logs
a single warning and no-ops (returning ``False``) rather than raising — the
scheduled run itself is unaffected.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class _SingleChannelBotOS:
    """Minimal ``BotOS``-shaped view exposing one platform bot.

    :class:`~praisonai_bot.bots.delivery.DeliveryRouter` only needs
    ``get_bot`` / ``list_bots``, so we avoid constructing a full ``BotOS``
    (and its supervisor / admission / lifecycle machinery) just to send one
    proactive message. Mirrors the gateway's ``_ChannelBotOS`` adapter, with
    the same case-insensitive lookup.
    """

    def __init__(self, bots: Dict[str, Any]) -> None:
        self._bots = bots

    def list_bots(self):
        return list(self._bots.keys())

    def get_bot(self, platform: str) -> Optional[Any]:
        bot = self._bots.get(platform)
        if bot is not None:
            return bot
        for name, candidate in self._bots.items():
            if name.lower() == platform.lower():
                return candidate
        return None


def _text_digest(text: str) -> str:
    """Short, stable digest of a delivery body for idempotency keys."""
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:16]


class SchedulerDelivery:
    """Resolve a ``deliver`` token and send scheduled results to a channel.

    A single instance is built per scheduler and reused across runs so the
    router's bounded idempotency LRU and per-platform rate limiters persist —
    a re-fired job delivering the *same* result to the *same* target is
    deduplicated in-process, exactly as on the gateway path.

    Args:
        deliver: The delivery token (e.g. ``"telegram:123456"``). An empty
            token disables delivery.
        job_id: Optional stable identifier folded into the idempotency key.
    """

    def __init__(self, deliver: str = "", *, job_id: str = "") -> None:
        self._deliver = deliver or ""
        self._job_id = job_id or ""
        self._router: Any = None
        self._bot: Any = None
        self._unavailable = False
        # Resolved once; the target grammar does not change across runs.
        self._target = self._parse_target(self._deliver)

    @staticmethod
    def _parse_target(deliver: str):
        if not deliver:
            return None
        try:
            from praisonaiagents.scheduler import DeliveryTarget
        except Exception as e:  # pragma: no cover - core always present
            logger.warning("Scheduler delivery: DeliveryTarget unavailable: %s", e)
            return None
        return DeliveryTarget.parse(deliver)

    @property
    def enabled(self) -> bool:
        """Whether a concrete delivery target was configured."""
        return self._target is not None

    def _ensure_router(self) -> bool:
        """Lazily build the platform bot + router. Returns True on success."""
        if self._router is not None:
            return True
        if self._unavailable or self._target is None:
            return False

        channel = (self._target.channel or "").strip()
        if not channel:
            symbolic = (self._target.deliver or self._deliver or "").strip().lower()
            if symbolic in ("origin", "all"):
                # 'origin' needs the original request's session context and
                # 'all' needs every configured bot — neither exists in this
                # lightweight single-channel path. Delivering these requires
                # the full BotOS gateway; tell the user how to target instead.
                logger.warning(
                    "Scheduler delivery: symbolic target '%s' cannot be "
                    "resolved by the lightweight scheduler delivery path "
                    "(no origin/session context). Use an explicit "
                    "'platform' or 'platform:channel_id' token, or run under "
                    "the full BotOS gateway.",
                    symbolic,
                )
            else:
                logger.warning(
                    "Scheduler delivery: token '%s' has no resolvable platform; "
                    "cannot deliver without the full gateway",
                    self._deliver,
                )
            self._unavailable = True
            return False

        try:
            from praisonai_bot.bots.bot import Bot
            from praisonai_bot.bots.delivery import DeliveryRouter
        except Exception as e:
            logger.warning(
                "Scheduler delivery configured (deliver=%r) but 'praisonai-bot' "
                "is not installed; result will not be delivered. Install the "
                "bot extra to enable channel delivery. (%s)",
                self._deliver,
                e,
            )
            self._unavailable = True
            return False

        try:
            self._bot = Bot(channel, enable_supervision=False)
            botos = _SingleChannelBotOS({channel: self._bot})
            self._router = DeliveryRouter(botos)
        except Exception as e:
            logger.warning(
                "Scheduler delivery: failed to build router for '%s': %s",
                channel,
                e,
            )
            self._unavailable = True
            return False
        return True

    def deliver(self, text: str) -> bool:
        """Deliver ``text`` to the configured target.

        Returns ``True`` if the router accepted the send, ``False`` otherwise
        (no target, package missing, resolution or send failure). Never raises:
        a delivery problem must not tear down the scheduler.
        """
        if self._target is None:
            return False
        if not self._ensure_router():
            return False

        channel = self._target.channel or ""
        channel_id = self._target.channel_id or ""
        thread_id = self._target.thread_id or ""
        # Prefer an explicit "platform:channel_id" target; fall back to the
        # bare platform token so the router resolves its home channel. The
        # router resolves to ``(platform, channel_id)`` and sends to the chat —
        # it does not (yet) route to a thread, so a ``thread_id`` narrows the
        # idempotency key (below) but is not part of the route.
        route = f"{channel}:{channel_id}" if channel_id else channel
        # Fold the thread into the dedup key so two threads in the same chat do
        # not collapse to one idempotency entry (which would drop the second
        # thread's message as a duplicate).
        idem = (
            f"sched:{self._job_id}:{channel}:{channel_id}:{thread_id}:"
            f"{_text_digest(text)}"
        )

        try:
            from praisonai._async_bridge import run_sync

            delivered = run_sync(
                self._router.deliver(route, text, idempotency_key=idem)
            )
        except Exception as e:
            logger.warning(
                "Scheduler delivery to '%s' failed: %s", route, e,
            )
            return False

        if delivered:
            logger.info("Scheduler delivered result to %s", route)
        else:
            logger.error("Scheduler failed to deliver result to %s", route)
        return bool(delivered)
