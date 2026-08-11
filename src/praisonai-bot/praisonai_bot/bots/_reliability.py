"""
Gateway reliability presets (Issue #2531).

The gateway ships strong reliability building blocks — a durable inbound
journal (default-on at the session level), a durable outbound outbox, gateway
-wide admission control, and graceful-shutdown draining. Historically the two
strongest lifecycle knobs (graceful drain and inbound admission) were
individually opt-in, so an operator running the gateway the "obvious" way
silently got a no-backpressure deployment that cut in-flight turns on restart.
As of Issue #3438 the *unset* posture is safe by default (bounded admission +
graceful drain, bind-aware); ``reliability="off"`` opts back into the old
immediate-teardown behaviour.

This module resolves a single, discoverable ``reliability`` preset onto the
already-existing :class:`BotOS` constructor arguments so the happy path is
production-grade in one switch, while explicit fields still win.

Safe by default (Issue #3438)
-----------------------------
Leaving ``reliability`` unset (``None``) now resolves to a *safe* posture
instead of the old no-backpressure one: a bounded admission ceiling + fair
wait queue and a graceful-drain window, so an operator running the gateway
the "obvious" way gets backpressure and does not cut in-flight turns on a
restart. The posture is bind-aware — a gateway bound to a non-loopback
interface (an actual deployment) resolves to the full ``production`` window,
while a loopback bind keeps the same admission ceiling with a snappier drain.
Opting back into today's immediate-teardown behaviour is an explicit
``reliability="off"``.

Profiles
--------
``"production"``
    Graceful drain (15s window), inbound admission with a CPU-scaled
    concurrency ceiling and a bounded fair wait queue.
``None`` (unset)
    Safe by default: bounded admission ceiling + fair wait queue plus a
    graceful-drain window, bind-aware (full ``production`` window when
    externally bound, a snappy 5s drain on loopback).
``"default"``
    The explicit legacy posture: a sane, small graceful-drain window (5s) so
    a restart doesn't cut in-flight turns, but no admission ceiling
    (unbounded, legacy dispatch). Durable inbound journal remains on by
    default (session level).
``"off"``
    Today's immediate-teardown behaviour: no drain, no admission.

Precedence
----------
Explicit constructor fields always override the preset. A caller passing
``drain_timeout=`` / ``max_concurrent_runs=`` / ``admission_policy=`` keeps
exactly that value; the preset only fills in the fields left unset.
"""

from __future__ import annotations

import ipaddress
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

# Non-IP hostnames that mean "not an actual external deployment". A bind to
# any of these (or to any loopback IP, detected numerically below) keeps the
# safe-by-default admission ceiling but with a snappy drain; anything else (a
# real interface) resolves to the full ``production`` window (Issue #3438).
_LOOPBACK_HOSTNAMES = frozenset({"", "localhost", "loopback"})


def _is_externally_bound(bind_host: Optional[str]) -> bool:
    """Whether *bind_host* looks like a real (non-loopback) deployment bind.

    ``0.0.0.0`` / ``::`` (bind-all) and any concrete non-loopback address count
    as external; ``None`` (unknown) is treated as loopback so we never guess a
    host is external without evidence. Loopback is detected numerically via
    :mod:`ipaddress`, so every valid loopback form — ``127.0.0.2``,
    ``127.255.255.255``, an expanded ``0:0:0:0:0:0:0:1`` — is recognised, not
    just the canonical ``127.0.0.1`` / ``::1`` spellings.
    """
    if bind_host is None:
        return False
    host = str(bind_host).strip().lower()
    if host in _LOOPBACK_HOSTNAMES:
        return False
    # Strip an IPv6 zone id / brackets, then classify numerically. A bare
    # hostname that isn't a literal IP (e.g. a DNS name) is treated as an
    # external bind — we only special-case the known loopback names above.
    candidate = host.strip("[]").split("%", 1)[0]
    try:
        return not ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return True


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
    # Per-conversation outbound delivery ordering for the durable outbox.
    # ``"strict"`` gives per-lane FIFO (production preset); ``"best_effort"``
    # keeps the historic global-order behaviour (default / off presets).
    outbound_ordering: str = "best_effort"


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
    bind_host: Optional[str] = None,
    drain_timeout: Optional[float] = None,
    max_concurrent_runs: int = 0,
    queue_depth: int = 0,
    overflow_policy: str = "reject",
    admission_policy: Optional[object] = None,
    outbound_ordering: Optional[str] = None,
) -> ResolvedReliability:
    """Compose a reliability preset with explicit constructor overrides.

    Args:
        reliability: Profile name (``"production"`` | ``"default"`` | ``"off"``)
            or ``None`` for the safe-by-default posture (Issue #3438).
        bind_host: The host the gateway binds to; informs the *unset* default
            posture — a non-loopback bind (an actual deployment) resolves to
            the full ``production`` window, loopback keeps a snappy drain.
            Ignored once an explicit preset is chosen.
        drain_timeout: Explicit graceful-drain window; ``None`` means "let the
            preset decide".
        max_concurrent_runs: Explicit admission ceiling; a positive value wins
            over the preset. ``0`` means "let the preset decide".
        queue_depth: Explicit bounded wait-queue depth (used with admission).
        overflow_policy: Explicit overflow behaviour when the queue is full.
        admission_policy: Explicit admission policy object; when supplied the
            preset does not synthesise admission knobs (the policy wins).
        outbound_ordering: Explicit per-conversation outbound ordering
            (``"strict"`` | ``"best_effort"``); ``None`` means "let the preset
            decide" (``strict`` for production, ``best_effort`` otherwise).

    Returns:
        A :class:`ResolvedReliability` carrying the effective knobs.
    """
    profile = normalize_reliability(reliability)

    # Safe by default (Issue #3438): an unset posture (``None``) resolves to a
    # backpressured deployment rather than the old no-admission one. A real
    # (non-loopback) bind becomes the full ``production`` posture; loopback
    # keeps the same admission ceiling with a snappier drain. An explicit
    # ``"default"`` / ``"off"`` / ``"production"`` is respected as-is.
    unset_default = profile is None
    if unset_default:
        profile = "production" if _is_externally_bound(bind_host) else "__safe__"

    # Start from the caller's explicit values (these always win).
    resolved_drain = drain_timeout
    resolved_max = int(max_concurrent_runs or 0)
    resolved_queue = int(queue_depth or 0)
    resolved_overflow = overflow_policy or "reject"

    explicit_admission = admission_policy is not None or resolved_max > 0

    if outbound_ordering is not None and outbound_ordering not in (
        "strict",
        "best_effort",
    ):
        raise ValueError(
            f"outbound_ordering must be 'strict' or 'best_effort', "
            f"got {outbound_ordering!r}"
        )
    # An explicit ordering always wins; otherwise the production posture and
    # the safe-by-default posture upgrade to strict per-lane FIFO, keeping the
    # explicit ``default``/``off`` presets backward compatible (best-effort).
    resolved_ordering = outbound_ordering or (
        "strict" if profile in ("production", "__safe__") else "best_effort"
    )

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
            outbound_ordering=resolved_ordering,
        )

    if profile in ("production", "__safe__"):
        # ``production`` and the loopback safe-default share the same admission
        # ceiling + bounded fair queue; they differ only in the drain window
        # (a real deployment gets the longer production window, loopback keeps
        # a snappy restart).
        if resolved_drain is None:
            resolved_drain = (
                _PRODUCTION_DRAIN_SECONDS
                if profile == "production"
                else _DEFAULT_DRAIN_SECONDS
            )
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
            outbound_ordering=resolved_ordering,
        )

    # profile == "default" (explicit legacy posture): a sane small drain window
    # so a restart does not cut in-flight turns, but no admission ceiling.
    if resolved_drain is None:
        resolved_drain = _DEFAULT_DRAIN_SECONDS
    return ResolvedReliability(
        drain_timeout=resolved_drain,
        max_concurrent_runs=resolved_max,
        queue_depth=resolved_queue,
        overflow_policy=resolved_overflow,
        outbound_ordering=resolved_ordering,
    )


__all__ = [
    "ResolvedReliability",
    "normalize_reliability",
    "resolve_reliability",
]
