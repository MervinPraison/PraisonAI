"""Notification gate for the proactive delivery path (Issue #6138).

Binds the pure core policy (:func:`praisonaiagents.push.policy.evaluate`) to the
gateway's ``notifications:`` config so :meth:`DeliveryRouter.deliver` can
enforce categories, quiet hours and detail-level redaction for every
categorised proactive send. The YAML block *is* the durable per-recipient store:

.. code-block:: yaml

    gateway:
      notifications:
        defaults: {detail: identified, categories: [approval_requested]}
        recipients:
          "telegram:12345":
            categories: [approval_requested, agent_finished]
            quiet_hours: "22:00-07:30"
            timezone: "Europe/London"
            detail: detailed

Recipients are keyed by the resolved ``platform:channel_id``. A recipient with
no entry falls back to ``defaults`` (or the core ``DEFAULT_PREFERENCE``).
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any, Dict, Mapping, Optional

from praisonaiagents.push.policy import (
    DEFAULT_PREFERENCE,
    DetailLevel,
    NotificationCategory,
    NotificationDecision,
    NotificationPreference,
    evaluate,
)


def _parse_time(value: str) -> time:
    hour, _, minute = str(value).strip().partition(":")
    return time(int(hour), int(minute or 0))


def parse_preference(
    raw: Mapping[str, Any], base: NotificationPreference = DEFAULT_PREFERENCE
) -> NotificationPreference:
    """Build a :class:`NotificationPreference` from a YAML/dict entry.

    Keys absent from ``raw`` inherit from ``base``. ``quiet_hours`` accepts a
    ``"HH:MM-HH:MM"`` string or a ``[start, end]`` pair. Invalid values raise
    ``ValueError`` so a typo fails at config load, not silently at send time.
    """
    categories = base.categories
    if "categories" in raw:
        categories = {NotificationCategory(c) for c in (raw["categories"] or [])}
    quiet = base.quiet_hours
    if "quiet_hours" in raw:
        window = raw["quiet_hours"]
        if window:
            start, end = window.split("-", 1) if isinstance(window, str) else window
            quiet = (_parse_time(start), _parse_time(end))
        else:
            quiet = None
    return NotificationPreference(
        categories=set(categories),
        quiet_hours=quiet,
        timezone=str(raw.get("timezone", base.timezone)),
        detail=DetailLevel(raw.get("detail", base.detail)),
        urgent_overrides_quiet=bool(
            raw.get("urgent_overrides_quiet", base.urgent_overrides_quiet)
        ),
    )


class NotificationGate:
    """Resolve a recipient's preference and evaluate one categorised send."""

    def __init__(self, config: Mapping[str, Any]):
        self._defaults = parse_preference(config.get("defaults") or {})
        self._recipients: Dict[str, NotificationPreference] = {
            str(key): parse_preference(raw or {}, self._defaults)
            for key, raw in (config.get("recipients") or {}).items()
        }

    def preference_for(self, recipient: str) -> NotificationPreference:
        return self._recipients.get(recipient, self._defaults)

    def admit(
        self,
        recipient: str,
        category: Any,
        content: Optional[str],
        *,
        identity: Optional[str] = None,
    ) -> NotificationDecision:
        # An aware UTC ``now`` lets the core localise to the recipient's own
        # timezone instead of the gateway host's wall clock.
        return evaluate(
            NotificationCategory(category),
            self.preference_for(recipient),
            now=datetime.now(timezone.utc),
            content=content,
            identity=identity,
        )
