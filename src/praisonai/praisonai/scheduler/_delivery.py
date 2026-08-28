"""Lightweight delivery for interval / scheduled agents.

Wires the wrapper :class:`~praisonai.scheduler.agent_scheduler.AgentScheduler`
``deliver=`` target to the *same* resilient delivery machinery BotOS uses —
without standing up the full gateway. It reuses:

- ``praisonaiagents.scheduler.DeliveryTarget`` — the core, serialisable target
  (parsed from a ``"telegram:123456"`` style token via ``DeliveryTarget.parse``).
- ``praisonai_bot.bots.delivery.DeliveryRouter`` — symbolic-target resolution,
  token-bucket rate limiting, durable (restart-safe) idempotency dedup and
  dead-target skip/self-heal. The router is injected with the same durable
  ``SqliteIdempotencyStore`` the gateway uses (issue #4541), so a job re-fired
  after a crash/restart is deduplicated across processes — not just in-process.

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
    router's per-platform rate limiters persist. Idempotency is now durable
    (issue #4541): the router is injected with the same ``SqliteIdempotencyStore``
    the gateway uses, so a re-fired job delivering the *same* result to the
    *same* target is deduplicated across restarts — restart-safe, exactly as on
    the gateway outbox path, not merely in-process.

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
        # Creation-time pre-flight (Issue #3800): answer "where will this go?"
        # the moment the send is configured instead of only at fire time. This
        # is a structural, registry-free check — an unrecognised symbolic token
        # or a token with no resolvable platform is surfaced now, with the
        # fire-time self-heal kept as the second line of defence for targets
        # that go dead *after* creation.
        v = self.validate()
        if not v.ok:
            logger.warning(
                "Scheduler delivery target %r is not routable: %s %s",
                self._deliver,
                v.reason,
                v.hint,
            )
        elif v.preview:
            logger.info("Scheduled -> %s", v.preview)

    def validate(self) -> "DeliveryValidation":
        """Pre-flight the configured delivery target at *creation* time.

        Resolves the target's well-formedness without a live channel registry
        so a typo'd or unroutable token is caught the moment the scheduled /
        agent-initiated send is created, rather than being silently dropped
        when the job fires hours later. Symbolic ``origin`` is accepted only
        when a concrete origin was persisted (otherwise there is nothing to
        deliver back to); ``all`` requires the full gateway and is flagged on
        the lightweight path; a bare token with no resolvable platform is
        rejected with an actionable hint. Returns a
        :class:`~praisonaiagents.gateway.DeliveryValidation`; never raises.
        """
        from praisonaiagents.gateway import DeliveryValidation

        if self._target is None:
            # No delivery configured is a valid state (delivery disabled).
            return DeliveryValidation(ok=True, preview="")

        preview = self._target.preview()
        channel = (self._target.channel or "").strip()
        if channel:
            return DeliveryValidation(ok=True, preview=preview)

        symbolic = (self._target.deliver or self._deliver or "").strip().lower()
        if symbolic == "origin":
            return DeliveryValidation(
                ok=False,
                reason=(
                    "'origin' target has no persisted origin to resolve "
                    "(job was not created with an origin channel)"
                ),
                hint=(
                    "Pass the job's origin, use an explicit 'platform' or "
                    "'platform:channel_id' token, or run under the full "
                    "BotOS gateway."
                ),
                preview=preview,
            )
        if symbolic == "all":
            return DeliveryValidation(
                ok=False,
                reason=(
                    "symbolic target 'all' cannot be resolved by the "
                    "lightweight scheduler delivery path"
                ),
                hint=(
                    "Use an explicit 'platform' or 'platform:channel_id' "
                    "token, or run under the full BotOS gateway."
                ),
                preview=preview,
            )
        return DeliveryValidation(
            ok=False,
            reason=f"token '{self._deliver}' has no resolvable platform",
            hint="Use a 'platform' or 'platform:channel_id' token.",
            preview=preview,
        )

    @property
    def preview(self) -> str:
        """Dry-run preview of the configured destination (empty if disabled)."""
        if self._target is None:
            return ""
        return self._target.preview()

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

    @staticmethod
    def _build_idempotency_store() -> Any:
        """Build the durable idempotency store the router dedups against (#4541).

        The lightweight path previously relied on the router's in-process LRU,
        which is empty after a restart — so a job re-fired across a crash could
        double-post (or, post-send/pre-record, drop). Injecting the same durable
        :class:`~praisonai_bot.bots._idempotency.SqliteIdempotencyStore` the
        gateway uses gives every path one restart-safe, effectively-once
        guarantee. The store lives under the same ``<home>/state`` path the
        gateway uses so gateway, lightweight and standalone ticks on one home
        converge on one dedup ledger. The home honours ``$PRAISONAI_HOME``
        (falling back to ``~/.praisonai``) so two isolated deployments under one
        OS account keep separate ledgers rather than cross-suppressing each
        other's deterministic delivery keys.

        Best-effort: any failure (missing bot extra, unwritable state dir)
        returns ``None`` so the router falls back to its LRU and delivery still
        works — durability degrades, it never blocks.
        """
        try:
            import os
            from pathlib import Path

            from praisonai_bot.bots._idempotency import build_idempotency_store

            base = os.environ.get("PRAISONAI_HOME")
            home = Path(base) if base else Path.home() / ".praisonai"
            path = home / "state" / "delivery.db"
            return build_idempotency_store("sqlite", path=path)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug(
                "Scheduler delivery: durable idempotency store unavailable "
                "(%s); falling back to in-process dedup",
                e,
            )
            return None

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
            self._router = DeliveryRouter(
                botos, idempotency_store=self._build_idempotency_store()
            )
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
        # Prefer an explicit "platform:channel_id[:thread_id]" target; fall back
        # to the bare platform token so the router resolves its home channel.
        # The router now preserves the thread segment end-to-end, so a thread
        # target is delivered into that thread rather than the parent chat.
        if channel_id and thread_id:
            route = f"{channel}:{channel_id}:{thread_id}"
        elif channel_id:
            route = f"{channel}:{channel_id}"
        else:
            route = channel
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
