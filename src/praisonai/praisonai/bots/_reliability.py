"""
Gateway reliability presets (Issue #2531).

The gateway ships strong reliability building blocks — a durable inbound
journal (default-on at the session level), a durable outbound outbox, gateway
-wide admission control, and graceful-shutdown draining — but the two strongest
lifecycle knobs (graceful drain and inbound admission) are individually opt-in.
An operator running the gateway the "obvious" way therefore silently gets a
no-backpressure deployment that cuts in-flight turns on restart.

This module resolves a single, discoverable ``reliability`` preset onto the
already-existing :class:`BotOS` constructor arguments so the happy path is
production-grade in one switch, while explicit fields still win.

Profiles
--------
``"production"``
    Graceful drain (15s window), inbound admission with a CPU-scaled
    concurrency ceiling and a bounded fair wait queue.
``"default"`` / ``None``
    A sane, small graceful-drain window (5s) so a restart doesn't cut
    in-flight turns, but no admission ceiling (unbounded, legacy dispatch).
    Durable inbound journal remains on by default (session level).
``"off"``
    Today's immediate-teardown behaviour: no drain, no admission.

Precedence
----------
Explicit constructor fields always override the preset. A caller passing
``drain_timeout=`` / ``max_concurrent_runs=`` / ``admission_policy=`` keeps
exactly that value; the preset only fills in the fields left unset.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

# Sane default graceful-drain window (seconds) applied when neither a preset
# nor an explicit ``drain_timeout`` selects one. Small enough to keep restarts
# snappy, long enough that a mid-turn reply is not cut on a rolling deploy.
_DEFAULT_DRAIN_SECONDS = 5.0

# Graceful-drain window for the ``production`` preset.
_PRODUCTION_DRAIN_SECONDS = 15.0

# Bounded wait-queue depth for the ``production`` preset — absorbs short bursts
# without letting the queue grow unbounded.
_PRODUCTION_QUEUE_DEPTH = 32

_KNOWN_PROFILES = ("production", "default", "off")


def _cpu_scaled_ceiling() -> int:
    """A conservative CPU-scaled default concurrency ceiling.

    Agent turns are latency-bound (provider calls) rather than CPU-bound, so we
    allow several turns per core while keeping a sane floor/ceiling so a burst
    can't fan out unboundedly.
    """
    try:
        cpus = os.cpu_count() or 2
    except Exception:  # pragma: no cover — defensive
        cpus = 2
    return max(4, min(32, cpus * 4))


@dataclass(frozen=True)
class ResolvedReliability:
    """The concrete knobs a reliability preset resolves to.

    ``None`` fields mean "leave the constructor default / explicit value in
    place"; non-``None`` fields are the preset-supplied values that fill unset
    constructor arguments.
    """

    drain_timeout: Optional[float]
    max_concurrent_runs: int
    queue_depth: int
    overflow_policy: str


def normalize_reliability(reliability: Optional[str]) -> Optional[str]:
    """Normalise a reliability value to a known profile name (or ``None``).

    Accepts ``None`` (unset → the ``default`` posture) and is case/space
    insensitive. Raises ``ValueError`` on an unknown profile so a typo fails
    fast rather than silently degrading robustness.
    """
    if reliability is None:
        return None
    if not isinstance(reliability, str):
        raise ValueError(
            f"reliability must be a string profile name, got {reliability!r}"
        )
    name = reliability.strip().lower()
    if name in ("", "none"):
        return None
    if name not in _KNOWN_PROFILES:
        raise ValueError(
            f"unknown reliability profile {reliability!r}; "
            f"expected one of {', '.join(_KNOWN_PROFILES)}"
        )
    return name


def resolve_reliability(
    reliability: Optional[str],
    *,
    drain_timeout: Optional[float] = None,
    max_concurrent_runs: int = 0,
    queue_depth: int = 0,
    overflow_policy: str = "reject",
    admission_policy: Optional[object] = None,
) -> ResolvedReliability:
    """Compose a reliability preset with explicit constructor overrides.

    Args:
        reliability: Profile name (``"production"`` | ``"default"`` | ``"off"``)
            or ``None`` for the default posture.
        drain_timeout: Explicit graceful-drain window; ``None`` means "let the
            preset decide".
        max_concurrent_runs: Explicit admission ceiling; a positive value wins
            over the preset. ``0`` means "let the preset decide".
        queue_depth: Explicit bounded wait-queue depth (used with admission).
        overflow_policy: Explicit overflow behaviour when the queue is full.
        admission_policy: Explicit admission policy object; when supplied the
            preset does not synthesise admission knobs (the policy wins).

    Returns:
        A :class:`ResolvedReliability` carrying the effective knobs.
    """
    profile = normalize_reliability(reliability)

    # Start from the caller's explicit values (these always win).
    resolved_drain = drain_timeout
    resolved_max = int(max_concurrent_runs or 0)
    resolved_queue = int(queue_depth or 0)
    resolved_overflow = overflow_policy or "reject"

    explicit_admission = admission_policy is not None or resolved_max > 0

    if profile == "off":
        # Preserve today's immediate-teardown / unbounded-dispatch behaviour,
        # but never override an explicit opt-in.
        if resolved_drain is None:
            resolved_drain = 0.0
        return ResolvedReliability(
            drain_timeout=resolved_drain,
            max_concurrent_runs=resolved_max,
            queue_depth=resolved_queue,
            overflow_policy=resolved_overflow,
        )

    if profile == "production":
        if resolved_drain is None:
            resolved_drain = _PRODUCTION_DRAIN_SECONDS
        if not explicit_admission:
            resolved_max = _cpu_scaled_ceiling()
            if resolved_queue <= 0:
                resolved_queue = _PRODUCTION_QUEUE_DEPTH
            # A bounded queue is the production-safe default; only fall back to
            # plain reject when the caller has said so explicitly.
            if overflow_policy == "reject":
                resolved_overflow = "queue"
        return ResolvedReliability(
            drain_timeout=resolved_drain,
            max_concurrent_runs=resolved_max,
            queue_depth=resolved_queue,
            overflow_policy=resolved_overflow,
        )

    # profile in (None, "default"): a sane small drain window so a restart does
    # not cut in-flight turns, but no admission ceiling by default.
    if resolved_drain is None:
        resolved_drain = _DEFAULT_DRAIN_SECONDS
    return ResolvedReliability(
        drain_timeout=resolved_drain,
        max_concurrent_runs=resolved_max,
        queue_depth=resolved_queue,
        overflow_policy=resolved_overflow,
    )


__all__ = [
    "ResolvedReliability",
    "normalize_reliability",
    "resolve_reliability",
]
