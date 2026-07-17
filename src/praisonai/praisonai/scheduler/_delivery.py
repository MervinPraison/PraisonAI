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
        origin: Optional persisted origin target (``ScheduleJob.origin``) — the
            concrete ``(channel, channel_id[, thread_id])`` where the job was
            created. When ``deliver`` is the symbolic ``"origin"`` token this is
            used to resolve a concrete route without the full gateway, so a
            scheduled/interval agent can deliver back to its point of origin on
            the lightweight path.
    """

    def __init__(
        self, deliver: str = "", *, job_id: str = "", origin: Any = None
    ) -> None:
        self._deliver = deliver or ""
        self._job_id = job_id or ""
        self._origin = origin
        self._router: Any = None
        self._bot: Any = None
        self._unavailable = False
        # Resolved once; the target grammar does not change across runs. A
        # symbolic ``"origin"`` token is rewritten to the persisted concrete
        # origin target here so the rest of the path treats it like any other
        # explicit ``channel:channel_id`` target — no live session required.
        self._target = self._resolve_origin_target(
            self._parse_target(self._deliver)
        )

    @staticmethod
    def origin_from_config(config: Optional[Dict[str, Any]]) -> Any:
        """Extract a persisted origin :class:`DeliveryTarget` from job config.

        A scheduled job persists where it was created on ``ScheduleJob.origin``.
        When that job is materialised into a scheduler the origin is carried in
        the ``config`` dict — either as a live :class:`DeliveryTarget` or as its
        serialised ``dict`` form (from ``to_dict`` / persisted state). Normalise
        both so ``deliver="origin"`` can resolve to the concrete channel on the
        lightweight path. Returns ``None`` when no usable origin is present.
        """
        if not config:
            return None
        origin = config.get("origin")
        if origin is None:
            return None
        if getattr(origin, "channel", None) is not None:
            return origin
        if isinstance(origin, dict):
            try:
                from praisonaiagents.scheduler import DeliveryTarget
            except Exception:  # pragma: no cover - core always present
                return None
            try:
                return DeliveryTarget.from_dict(origin)
            except Exception:
                return None
        return None

    def _resolve_origin_target(self, target: Any) -> Any:
        """Rewrite a symbolic ``origin`` target to the persisted concrete one.

        When ``deliver`` is ``"origin"`` the parsed target carries no channel;
        the job's origin was captured at creation and persisted as a concrete
        :class:`DeliveryTarget`. Substitute it so the lightweight path can
        deliver back to the point of origin without the full gateway. Any other
        target (explicit ``channel:channel_id``, bare platform, or ``all``) is
        returned unchanged.
        """
        if target is None:
            return None
        symbolic = (target.deliver or "").strip().lower()
        if symbolic != "origin":
            return target
        origin = self._origin
        if origin is None or not getattr(origin, "channel", ""):
            return target
        try:
            from praisonaiagents.scheduler import DeliveryTarget
        except Exception:  # pragma: no cover - core always present
            return target
        channel = origin.channel
        channel_id = origin.channel_id or ""
        thread_id = origin.thread_id
        token = f"{channel}:{channel_id}" if channel_id else channel
        if thread_id:
            token = f"{token}:{thread_id}"
        return DeliveryTarget(
            channel=channel,
            channel_id=channel_id,
            thread_id=thread_id,
            deliver=token,
        )

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
            if symbolic == "origin":
                # 'origin' is resolvable on this lightweight path when the job
                # persisted a concrete origin target (rewritten in
                # ``_resolve_origin_target``). Reaching here means no origin was
                # captured, so there is nothing concrete to deliver back to.
                logger.warning(
                    "Scheduler delivery: 'origin' target has no persisted "
                    "origin to resolve (job was not created with an origin "
                    "channel). Pass the job's origin, use an explicit "
                    "'platform' or 'platform:channel_id' token, or run under "
                    "the full BotOS gateway.",
                )
            elif symbolic == "all":
                # 'all' needs every configured bot, which the lightweight
                # single-channel path cannot enumerate. Delivering it requires
                # the full BotOS gateway; tell the user how to target instead.
                logger.warning(
                    "Scheduler delivery: symbolic target 'all' cannot be "
                    "resolved by the lightweight scheduler delivery path "
                    "(cannot enumerate every configured bot). Use an explicit "
                    "'platform' or 'platform:channel_id' token, or run under "
                    "the full BotOS gateway.",
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
