"""Notification policy for gateway push — pure, dependency-free core.

The push stack elsewhere is transport + delivery-guarantee only: it can get
bytes to a device reliably, but it has no notion of *whether* or *what* to
notify. This module supplies that missing policy layer as pure protocol code so
every notifier (the gateway's delivery manager, scheduler completions,
background-job alerts) can make the same decision identically:

    decision = evaluate(category, prefs, now=..., is_urgent=..., content=...)
    if decision.send:
        deliver(recipient, decision.redacted_content)

Three concerns compose into one :class:`NotificationDecision`:

* **Categories** — a recipient opts in per event class (``approval_requested``,
  ``agent_finished`` …); an un-opted category is suppressed.
* **Quiet hours** — a per-recipient local window suppresses non-urgent
  categories; urgent categories may override (``urgent_overrides_quiet``).
* **Detail level** — ``private`` / ``identified`` / ``detailed`` redacts how
  much message content leaves the gateway in a device notification.

The heavy enforcement + durable preference store + CLI/YAML surface live in the
``praisonai``/``praisonai-bot`` wrapper; this stays pure so it carries no heavy
imports and is trivially testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Optional, Set

__all__ = [
    "NotificationCategory",
    "DetailLevel",
    "NotificationPreference",
    "NotificationDecision",
    "evaluate",
    "DEFAULT_PREFERENCE",
]


class NotificationCategory(str, Enum):
    """Event classes a recipient can subscribe to independently."""

    APPROVAL_REQUESTED = "approval_requested"
    AGENT_FINISHED = "agent_finished"
    AGENT_QUESTION = "agent_question"
    HUMAN_MENTIONED = "human_mentioned"
    SCHEDULED_TASK_FAILED = "scheduled_task_failed"
    BACKGROUND_TASK_FAILED = "background_task_failed"


class DetailLevel(str, Enum):
    """How much content leaves the gateway in a notification.

    * ``PRIVATE`` — a bare "you have activity"; no agent/session, no content.
    * ``IDENTIFIED`` — which agent/session, but no message content.
    * ``DETAILED`` — content included verbatim.
    """

    PRIVATE = "private"
    IDENTIFIED = "identified"
    DETAILED = "detailed"


def _in_quiet_window(now: time, start: time, end: time) -> bool:
    """Whether ``now`` falls inside the ``[start, end)`` local window.

    Handles a window that wraps past midnight (e.g. ``22:00``–``07:30``) by
    treating start > end as "outside the daytime gap".
    """
    if start == end:
        return False
    if start < end:
        return start <= now < end
    return now >= start or now < end


@dataclass
class NotificationPreference:
    """A recipient's durable notification policy.

    Attributes:
        categories: Opted-in categories; a category not present is suppressed.
        quiet_hours: Optional ``(start, end)`` local time window during which
            non-urgent categories are suppressed. ``None`` means no quiet hours.
        timezone: IANA name used to localise ``now`` for the quiet-hours test.
        detail: Redaction level applied to the notification content.
        urgent_overrides_quiet: When True, an urgent event is delivered even
            inside quiet hours.
    """

    categories: Set[NotificationCategory] = field(default_factory=set)
    quiet_hours: Optional[tuple] = None
    timezone: str = "UTC"
    detail: DetailLevel = DetailLevel.IDENTIFIED
    urgent_overrides_quiet: bool = True

    def allows(self, category: NotificationCategory) -> bool:
        """Whether this recipient has opted into ``category``."""
        return category in self.categories


# A sensible default applied when a recipient has set nothing: the two
# interaction-blocking categories are on, at the identified (no-content) detail
# level, with no quiet hours.
DEFAULT_PREFERENCE = NotificationPreference(
    categories={
        NotificationCategory.APPROVAL_REQUESTED,
        NotificationCategory.AGENT_QUESTION,
    },
    detail=DetailLevel.IDENTIFIED,
)


@dataclass
class NotificationDecision:
    """Outcome of :func:`evaluate` for one (category, recipient, moment).

    Attributes:
        send: Whether the notification should be delivered at all.
        reason: Machine/operator-readable reason (e.g. ``"quiet_hours"``,
            ``"category_not_subscribed"``, ``"ok"``).
        redacted_content: The content to actually push, redacted per the
            recipient's detail level (``None`` when ``send`` is False).
    """

    send: bool
    reason: str
    redacted_content: Optional[str] = None


def _redact(detail: DetailLevel, content: Optional[str], identity: Optional[str]) -> str:
    """Apply the detail-level redaction to ``content``.

    ``identity`` is an agent/session label used at the ``identified`` level so a
    recipient learns *what* has activity without the transcript leaving the
    gateway.
    """
    if detail == DetailLevel.DETAILED:
        return content if content is not None else "You have new activity"
    if detail == DetailLevel.IDENTIFIED:
        return f"Activity in {identity}" if identity else "You have new activity"
    return "You have new activity"


def evaluate(
    category: NotificationCategory,
    prefs: Optional[NotificationPreference] = None,
    *,
    now: Optional[datetime] = None,
    is_urgent: bool = False,
    content: Optional[str] = None,
    identity: Optional[str] = None,
) -> NotificationDecision:
    """Decide whether/what to notify for one event — pure, no side effects.

    Args:
        category: The event class being considered.
        prefs: The recipient's preference; ``DEFAULT_PREFERENCE`` when ``None``.
        now: The moment of evaluation (defaults to ``datetime.now`` localised to
            the recipient's timezone). A naive ``now`` is treated as already in
            the recipient's local zone.
        is_urgent: Whether this specific event is urgent (may override quiet
            hours when the recipient allows it).
        content: The full message content, redacted per ``prefs.detail``.
        identity: An agent/session label used at the ``identified`` detail level.

    Returns:
        A :class:`NotificationDecision`. ``send`` is False (with a ``reason``)
        when the category is not subscribed or quiet hours suppress it.
    """
    if prefs is None:
        prefs = DEFAULT_PREFERENCE

    if not prefs.allows(category):
        return NotificationDecision(send=False, reason="category_not_subscribed")

    if prefs.quiet_hours is not None:
        local_now = _localised_time(now, prefs.timezone)
        start, end = prefs.quiet_hours
        if _in_quiet_window(local_now, start, end):
            if not (is_urgent and prefs.urgent_overrides_quiet):
                return NotificationDecision(send=False, reason="quiet_hours")

    return NotificationDecision(
        send=True,
        reason="urgent_override" if is_urgent and prefs.quiet_hours else "ok",
        redacted_content=_redact(prefs.detail, content, identity),
    )


def _localised_time(now: Optional[datetime], tz_name: str) -> time:
    """Return the wall-clock ``time`` at ``now`` in ``tz_name``.

    A ``None`` ``now`` uses the current time. An aware ``now`` is converted to
    ``tz_name``; a naive ``now`` is assumed to already be local. ``zoneinfo`` is
    stdlib (3.9+) so this stays dependency-free; an unknown zone falls back to
    the naive time rather than raising.
    """
    if now is None:
        now = datetime.now()
    if now.tzinfo is not None:
        try:
            from zoneinfo import ZoneInfo

            now = now.astimezone(ZoneInfo(tz_name))
        except Exception:
            pass
    return now.timetz().replace(tzinfo=None) if now.tzinfo else now.time()
