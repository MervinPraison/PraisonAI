"""
Incident tracking for scheduled jobs — pure, dependency-free decision logic.

A scheduled automation running unattended may silently start failing. Per-run
history (:class:`RunRecord`) records *that* a tick failed, but nothing groups
repeated failures, detects recovery, or de-duplicates an operator alert — so a
broken nightly job either goes unnoticed or (if any alert were wired) re-fires
on every tick (alert fatigue).

This module is the shared "incident brain": it groups failures into durable
:class:`Incident` records keyed by a stable :func:`error_signature`, and a pure
:class:`IncidentTracker` that decides — from the stream of :class:`RunRecord`
observations — **when an operator should actually be told**:

* alert **once** per incident (first failure of a signature),
* **not again** for the same signature until it changes or recovers,
* a changed error message mints a **new** incident (re-alert),
* the next success **resolves** the open incident (single recovery note),
* optionally alert only after **N consecutive** failures (tolerate blips).

The tracker owns only the *policy* (what counts as an incident, when to alert).
It holds no I/O: a wrapper/gateway persists the returned incidents and delivers
the alert via the job's existing ``DeliveryTarget`` — so every execution engine
(gateway tick, wrapper, standalone) shares one incident brain (DRY).
"""

import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional


# Normalise volatile tokens out of an error so "429 rate limit (req id abc)" and
# "429 rate limit (req id xyz)" collapse to the *same* signature — otherwise
# every retry mints a "new" incident and re-alerts (the fatigue we prevent).
#
# We must NOT blanket-delete every digit run: a short number is frequently the
# *category* of the failure (HTTP status 404 vs 500, error/exit code 12 vs 34).
# Dropping it would collapse genuinely different failures onto one signature and
# suppress the required re-alert (Greptile P1). So we strip only clearly volatile
# numbers — long digit runs (timestamps, epochs, pids, ports, request ids) — and
# any number glued to letters (``req42``, ``id7f`` fragments) while KEEPING short
# standalone codes (1–3 digits) that carry meaning.
_HEX_RE = re.compile(r"0x[0-9a-fA-F]+|\b[0-9a-fA-F]{8,}\b")
# Digits fused to an adjacent letter/underscore (e.g. "worker3", "id42") are ids,
# not categories — drop the whole alnum run so it can't leak a volatile number.
_ALNUM_ID_RE = re.compile(r"\b(?=\w*\d)(?=\w*[a-z])\w+\b")
# Long standalone digit runs (>= 4) are volatile (timestamps, epochs, pids); a
# short run (1–3 digits) is a meaningful code and is preserved verbatim.
_LONG_NUM_RE = re.compile(r"\b\d{4,}\b")
_WS_RE = re.compile(r"\s+")
_SIGNATURE_PREFIX_CHARS = 200


def normalise_error(error: str) -> str:
    """Return a stable, comparable form of an error message.

    Lower-cases and strips *volatile* tokens — hex ids / UUID-ish blobs, long
    digit runs (timestamps, epochs, pids, request ids) and numbers fused into
    identifier-like words — then collapses whitespace and keeps a bounded
    prefix. Short standalone numeric codes (HTTP status, error/exit codes) are
    **preserved** so genuinely different failures (``404`` vs ``500``) keep
    distinct signatures and re-alert, while a changing request id does not mint
    a new incident every retry.
    """
    text = (error or "").strip().lower()
    text = _HEX_RE.sub("", text)
    text = _ALNUM_ID_RE.sub("", text)
    text = _LONG_NUM_RE.sub("", text)
    text = _WS_RE.sub(" ", text).strip()
    return text[:_SIGNATURE_PREFIX_CHARS]


def error_signature(error: str) -> str:
    """Return a stable ``sha256`` signature for an error message.

    Failures sharing a :func:`normalise_error` form share a signature, so the
    tracker groups them into one incident and alerts once; a genuinely
    different error yields a different signature and re-alerts.
    """
    return hashlib.sha256(normalise_error(error).encode("utf-8")).hexdigest()


@dataclass
class Incident:
    """A durable grouping of repeated failures for one job + error signature.

    Lifecycle: ``detected`` (a failure seen, threshold not yet met) →
    ``alerted`` (the operator has been told once) → ``resolved`` (a later
    success closed it). A changed error signature is a *new* incident.

    Attributes:
        job_id: ID of the failing job.
        signature: Stable :func:`error_signature` grouping the failures.
        state: Lifecycle state (``detected`` / ``alerted`` / ``resolved``).
        error: The most recent raw error message (for display in the alert).
        first_seen: Epoch seconds of the first failure in this incident.
        last_seen: Epoch seconds of the most recent failure.
        count: Number of failing ticks grouped into this incident.
        job_name: Human-readable job name for display.
    """

    job_id: str
    signature: str
    state: Literal["detected", "alerted", "resolved"] = "detected"
    error: Optional[str] = None
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    count: int = 0
    job_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "signature": self.signature,
            "state": self.state,
            "error": self.error,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "count": self.count,
            "job_name": self.job_name,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Incident":
        return cls(
            job_id=d.get("job_id", ""),
            signature=d.get("signature", ""),
            state=d.get("state", "detected"),
            error=d.get("error"),
            first_seen=d.get("first_seen", time.time()),
            last_seen=d.get("last_seen", time.time()),
            count=d.get("count", 0),
            job_name=d.get("job_name", ""),
        )


class IncidentTracker:
    """Pure latching policy that turns a stream of runs into de-duped alerts.

    Feed each :class:`RunRecord` to :meth:`observe`. It returns an
    :class:`Incident` **only when an operator alert is due** — the first time a
    failure signature crosses the threshold — and ``None`` on every subsequent
    identical failure (already alerted) or on a plain success with no open
    incident. A success that closes an open incident returns the now-``resolved``
    incident once (a single recovery note); a *different* error mints and alerts
    a new incident.

    State is a small per-job dict, so it round-trips through any
    :class:`JobStateStoreProtocol` the wrapper already provides — no new
    persistence surface. Construct one tracker per policy and reuse it; the
    per-job open-incident is carried in the ``state`` you pass back in.

    Args:
        after_failures: Alert only after this many *consecutive* failures of
            the same signature (default 1 = alert on the first failure). Values
            below 1 are treated as 1.
    """

    def __init__(self, after_failures: int = 1):
        self.after_failures = max(int(after_failures), 1)

    def observe(
        self,
        record: Any,
        state: Optional[Dict[str, Any]] = None,
    ) -> Optional[Incident]:
        """Fold one run into the incident state; return an alert-due incident.

        Args:
            record: A :class:`RunRecord` (or any object exposing ``status``,
                ``error``, ``job_id``, ``job_name``, ``timestamp``).
            state: The per-job incident state carried between observations
                (mutated in place). Pass the same dict back each tick — e.g.
                loaded from / saved to a :class:`JobStateStoreProtocol`.

        Returns:
            An :class:`Incident` when the operator should be alerted (a newly
            latched failure) or notified of a recovery (a just-``resolved``
            incident), otherwise ``None``.
        """
        if state is None:
            state = {}
        status = getattr(record, "status", None)

        if status == "failed":
            return self._observe_failure(record, state)
        if status == "succeeded":
            return self._observe_success(record, state)
        # ``skipped`` / ``no_change`` are neither failure nor recovery: they do
        # not open, advance, or close an incident.
        return None

    # ── internals ────────────────────────────────────────────────────

    def _observe_failure(
        self, record: Any, state: Dict[str, Any]
    ) -> Optional[Incident]:
        error = getattr(record, "error", None) or ""
        signature = error_signature(error)
        ts = getattr(record, "timestamp", None) or time.time()
        job_id = getattr(record, "job_id", "") or ""
        job_name = getattr(record, "job_name", "") or ""

        open_inc = state.get("incident")
        if open_inc and open_inc.get("signature") == signature and open_inc.get("state") != "resolved":
            # Same ongoing failure: advance counters; alert again only if the
            # threshold is only now crossed and we have not alerted yet.
            open_inc["count"] = open_inc.get("count", 0) + 1
            open_inc["last_seen"] = ts
            open_inc["error"] = error
            state["consecutive"] = state.get("consecutive", 0) + 1
            if (
                open_inc.get("state") == "detected"
                and state["consecutive"] >= self.after_failures
            ):
                open_inc["state"] = "alerted"
                return Incident.from_dict(open_inc)
            return None

        # A new (or changed) failure signature mints a fresh incident. Any
        # prior open incident is implicitly superseded (a different error).
        incident = Incident(
            job_id=job_id,
            signature=signature,
            state="detected",
            error=error,
            first_seen=ts,
            last_seen=ts,
            count=1,
            job_name=job_name,
        )
        state["incident"] = incident.to_dict()
        state["consecutive"] = 1
        if self.after_failures <= 1:
            incident.state = "alerted"
            state["incident"]["state"] = "alerted"
            return incident
        return None

    def _observe_success(
        self, record: Any, state: Dict[str, Any]
    ) -> Optional[Incident]:
        state["consecutive"] = 0
        open_inc = state.get("incident")
        if not open_inc or open_inc.get("state") == "resolved":
            return None
        ts = getattr(record, "timestamp", None) or time.time()
        was_alerted = open_inc.get("state") == "alerted"
        open_inc["state"] = "resolved"
        open_inc["last_seen"] = ts
        resolved = Incident.from_dict(open_inc)
        # Clear the open incident so a later failure of the same signature
        # correctly mints and alerts a fresh incident.
        state.pop("incident", None)
        # Only emit a recovery note if the operator was actually alerted — a
        # sub-threshold blip that never alerted should not send "recovered".
        if was_alerted:
            return resolved
        return None
