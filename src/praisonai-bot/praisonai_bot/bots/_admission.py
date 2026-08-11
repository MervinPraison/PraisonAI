"""
Gateway-wide inbound admission control (Issue #2454).

The gateway protects the *outbound* path (slow-consumer eviction, bounded send
queues, send-rate limiting) and serialises runs *per user*, but it has no
gateway-wide ceiling on concurrent inbound agent runs. A burst of inbound
traffic from many distinct users therefore translates directly into a burst of
concurrent provider calls — risking ``429`` storms, latency collapse and OOM,
with no graceful shed path.

``AdmissionGate`` is the wrapper-side enforcement of the core
``GatewayConcurrencyPolicyProtocol`` decision contract. It owns the live
mechanism — an :class:`asyncio.Semaphore` concurrency ceiling plus a bounded
wait queue — that the pure policy cannot (it needs the running event loop).
Each inbound turn asks the policy whether to admit, queue, or reject; the gate
then either runs immediately, waits for a slot (bounded), or sheds with a busy
acknowledgement.

The gate is intentionally lightweight and reuses the exact primitive already
proven for the background task runner
(``praisonaiagents/background/runner.py``: ``asyncio.Semaphore``). When no
ceiling is configured (``max_concurrent_runs <= 0``) the gate is a transparent
no-op so legacy behaviour is preserved bit-for-bit.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import sys
from contextlib import asynccontextmanager
from typing import Dict, Optional

try:
    # ``resource`` is Unix-only; on Windows the stdlib fallback is unavailable
    # and the sampler self-disables (psutil, if installed, still works).
    import resource  # type: ignore
except ImportError:  # pragma: no cover - Windows / platforms without resource
    resource = None  # type: ignore

logger = logging.getLogger(__name__)


class _RssSampler:
    """Lightweight, dependency-free RSS sampler for admission pressure checks.

    Reads the process resident-set size, preferring ``psutil`` (a live,
    monotonic RSS) when installed and falling back to stdlib
    ``resource.getrusage`` (``ru_maxrss`` — a *peak*, good enough to catch a
    climbing leak). If the platform can report neither, it self-disables after
    a single warning so the monitor never crashes the gateway it protects.
    """

    def __init__(self) -> None:
        self._psutil_proc = None
        self._disabled = False
        self._warned = False
        try:
            import psutil  # type: ignore

            self._psutil_proc = psutil.Process()
        except Exception:  # psutil optional — fall back to stdlib.
            self._psutil_proc = None

    def read(self):
        """Return a :class:`ResourceSample`; ``rss_mb=None`` if unavailable."""
        from praisonaiagents.gateway import ResourceSample

        if self._disabled:
            return ResourceSample(rss_mb=None)
        rss_mb = self._read_rss_mb()
        if rss_mb is None and not self._warned:
            self._warned = True
            self._disabled = True
            logger.warning(
                "AdmissionGate: resource sampling unavailable on this "
                "platform; memory-pressure admission disabled."
            )
        return ResourceSample(rss_mb=rss_mb)

    def _read_rss_mb(self) -> Optional[float]:
        proc = self._psutil_proc
        if proc is not None:
            try:
                return proc.memory_info().rss / (1024.0 * 1024.0)
            except Exception:  # pragma: no cover — defensive
                self._psutil_proc = None
        if resource is None:  # Windows / no stdlib ``resource`` and no psutil.
            return None
        try:
            maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        except Exception:  # pragma: no cover — platform without getrusage
            return None
        if not maxrss:
            return None
        # ru_maxrss is kilobytes on Linux, bytes on macOS/BSD.
        divisor = 1024.0 if sys.platform == "darwin" else 1.0
        return maxrss / divisor / 1024.0


class AdmissionRejected(Exception):
    """Raised when an inbound turn is shed because the gateway is at capacity.

    Carries a model-readable :attr:`message` so the caller can surface a clean
    busy acknowledgement to the user instead of an opaque error.
    """

    def __init__(self, message: str = "Busy right now — please resend in a moment."):
        super().__init__(message)
        self.message = message


class AdmissionGate:
    """Gateway-wide admission gate enforcing a concurrency ceiling + wait queue.

    Wraps a :class:`GatewayConcurrencyPolicyProtocol` (typically
    :class:`praisonaiagents.gateway.ConcurrencyLimitPolicy`). The policy owns
    the *decision* (admit / queue / reject); this owns the *mechanism*:

    * an :class:`asyncio.Semaphore` bounding simultaneously-running turns to
      ``max_concurrent_runs``, and
    * a counter of turns currently waiting for a slot, bounded by
      ``queue_depth``.

    Observability counters (:attr:`in_flight`, :attr:`queued`, :attr:`admitted`,
    :attr:`rejected`) are surfaced for health/metrics.

    Usage::

        gate = AdmissionGate(policy)
        async with gate.admit(session_id=user_id):
            return await run_the_turn()

    When the policy rejects, :meth:`admit` raises :class:`AdmissionRejected`
    before the body runs, so the caller can return a busy ack.
    """

    def __init__(
        self,
        policy: Optional[object],
        *,
        resource_policy: Optional[object] = None,
        resource_sampler: Optional[object] = None,
    ):
        self._policy = policy
        # Optional memory/resource-pressure policy (Issue #3445). When set, a
        # lightweight RSS sample is folded into each admit decision so the gate
        # queues under soft pressure and sheds under hard pressure before the
        # OOM killer fires. A ``None`` policy (or one that reports no threshold)
        # leaves admission concurrency-only, bit-for-bit as before.
        self._resource_policy = resource_policy
        self._resource_sampler = (
            resource_sampler
            if resource_sampler is not None
            else (_RssSampler() if resource_policy is not None else None)
        )
        # Lazily-created so the gate can be constructed off the event loop
        # (e.g. during BotOS.__init__) and bound to whichever loop runs it.
        self._sem: Optional[asyncio.Semaphore] = None
        self._max = int(getattr(policy, "max_concurrent_runs", 0) or 0)
        self._queue_depth = int(getattr(policy, "queue_depth", 0) or 0)
        self._overflow = str(getattr(policy, "overflow_policy", "reject") or "reject")
        # Live counters.
        self._in_flight = 0
        self._queued = 0
        # Cumulative observability.
        self.admitted = 0
        self.rejected = 0
        self.shed = 0
        # FIFO registry of in-progress waiters, keyed by monotonic ticket, used
        # to evict the *oldest* waiter under the ``shed_oldest`` overflow policy.
        self._waiters: "Dict[int, asyncio.Event]" = {}
        self._ticket = itertools.count()

    @property
    def _resource_enabled(self) -> bool:
        """Whether a resource-pressure policy with a live threshold is set."""
        pol = self._resource_policy
        if pol is None or self._resource_sampler is None:
            return False
        # A policy exposing ``enabled`` self-reports whether a threshold is set;
        # otherwise assume active (it was explicitly supplied).
        return bool(getattr(pol, "enabled", True))

    @property
    def enabled(self) -> bool:
        """Whether the gate is active.

        Active when a concurrency ceiling is set (a positive ``max``) or a
        resource-pressure policy with a live threshold is configured, so a
        memory-only deployment (no CPU ceiling) still sheds under RSS pressure.
        """
        if self._policy is not None and self._max > 0:
            return True
        return self._resource_enabled

    @property
    def in_flight(self) -> int:
        """Number of turns currently running."""
        return self._in_flight

    @property
    def queued(self) -> int:
        """Number of turns currently waiting for a slot."""
        return self._queued

    def stats(self) -> dict:
        """Return a snapshot of admission counters for health/metrics."""
        return {
            "max_concurrent_runs": self._max,
            "queue_depth": self._queue_depth,
            "in_flight": self._in_flight,
            "queued": self._queued,
            "admitted": self.admitted,
            "rejected": self.rejected,
            "shed": self.shed,
            "max_rss_mb": float(
                getattr(self._resource_policy, "hard_rss_mb", 0.0) or 0.0
            ),
        }

    def _ensure_sem(self) -> asyncio.Semaphore:
        if self._sem is None:
            # A resource-only gate (no concurrency ceiling, ``_max == 0``) still
            # needs a working semaphore for the shed path, so fall back to a
            # large-but-finite ceiling that never blocks on concurrency alone —
            # only the resource policy sheds there.
            #
            # Note (soft pressure, resource-only): with no concurrency ceiling
            # there is no slot to wait on, so a soft-pressure QUEUE degrades to
            # ADMIT here (it cannot delay a turn on its own). Real wait-queue
            # backpressure needs a concurrency ceiling (``max_concurrent_runs``)
            # alongside ``max_rss_mb``; the OOM-critical hard threshold always
            # REJECTs regardless. This is intentional: we do not spin a timer
            # loop to poll RSS (scope creep) — hard shedding is what prevents the
            # OOM kill, and soft pressure is advisory unless a ceiling exists.
            ceiling = self._max if self._max > 0 else 2**31 - 1
            self._sem = asyncio.Semaphore(ceiling)
        return self._sem

    @asynccontextmanager
    async def admit(self, *, session_id: str = ""):
        """Admit (or shed) an inbound turn, holding a slot for its duration.

        Yields when capacity is available (immediately or after waiting in the
        bounded queue). Raises :class:`AdmissionRejected` when the policy sheds
        the turn. A no-op pass-through when the gate is disabled.
        """
        if not self.enabled:
            # Disabled: preserve legacy always-admit behaviour with no overhead.
            yield
            return

        decision = self._decide(session_id=session_id)

        # Local import keeps core optional and avoids a hard import cycle.
        from praisonaiagents.gateway import AdmissionDecision

        if decision is AdmissionDecision.REJECT:
            self.rejected += 1
            logger.info(
                "AdmissionGate: rejecting turn (in_flight=%d queued=%d max=%d) "
                "session=%s",
                self._in_flight,
                self._queued,
                self._max,
                session_id or "-",
            )
            raise AdmissionRejected()

        sem = self._ensure_sem()
        waited = decision is AdmissionDecision.QUEUE
        shed_event: Optional[asyncio.Event] = None
        ticket: Optional[int] = None
        if waited:
            # Under ``shed_oldest``, a newcomer arriving at a full queue evicts
            # the oldest in-progress waiter so the queue can't grow unbounded.
            # If no live waiter can actually be shed (e.g. every queued waiter is
            # already signalled but still mid-cleanup), there is no slot to free,
            # so reject the newcomer rather than letting the wait set grow past
            # ``queue_depth``.
            if self._overflow == "shed_oldest" and self._queued >= self._queue_depth:
                if not self._shed_oldest_waiter():
                    self.rejected += 1
                    raise AdmissionRejected()
            self._queued += 1
            ticket = next(self._ticket)
            shed_event = asyncio.Event()
            self._waiters[ticket] = shed_event

        try:
            if shed_event is not None:
                # Race the slot acquisition against an eviction signal. Whichever
                # resolves first wins; the loser is cancelled cleanly.
                acquire_task = asyncio.ensure_future(sem.acquire())
                shed_task = asyncio.ensure_future(shed_event.wait())
                done, pending = await asyncio.wait(
                    {acquire_task, shed_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()
                # The eviction signal takes priority: if we were shed we must
                # NOT run, even in the race where the slot also became available
                # in the same wakeup. Release any acquired slot and reject.
                if shed_event.is_set():
                    if acquire_task in done and not acquire_task.cancelled():
                        sem.release()
                    self.shed += 1
                    raise AdmissionRejected()
                # Not evicted: ensure we hold a slot (consume the settled task or
                # acquire if it was still pending when shed lost the race).
                if acquire_task in pending:
                    await sem.acquire()
            else:
                await sem.acquire()
        finally:
            if ticket is not None:
                self._waiters.pop(ticket, None)
                self._queued -= 1

        self._in_flight += 1
        self.admitted += 1
        try:
            yield
        finally:
            self._in_flight -= 1
            sem.release()

    def _shed_oldest_waiter(self) -> bool:
        """Signal the oldest in-progress waiter to shed, freeing a queue slot.

        Returns ``True`` if a live (not-yet-signalled) waiter was evicted, or
        ``False`` when no waiter could be shed (every queued waiter is already
        signalled and mid-cleanup), so the caller knows no slot was actually
        freed and must not enqueue past ``queue_depth``.
        """
        for ticket in list(self._waiters):
            event = self._waiters.get(ticket)
            if event is not None and not event.is_set():
                event.set()
                return True
        return False

    def _decide(self, *, session_id: str):
        from praisonaiagents.gateway import AdmissionDecision

        decision = AdmissionDecision.ADMIT
        decide = getattr(self._policy, "decide", None)
        if decide is not None:
            try:
                decision = decide(
                    in_flight=self._in_flight,
                    queued=self._queued,
                    session_id=session_id,
                )
            except Exception as e:  # pragma: no cover — defensive: never block on policy error
                logger.warning(
                    "AdmissionGate: policy.decide failed (%s); admitting", e
                )
                decision = AdmissionDecision.ADMIT

        # Fold in memory/resource pressure (Issue #3445): take the more
        # restrictive of the concurrency and resource decisions so a soft RSS
        # breach queues and a hard breach sheds, before the OOM killer fires.
        resource_decision = self._resource_decide()
        return self._escalate(decision, resource_decision)

    def _resource_decide(self):
        from praisonaiagents.gateway import AdmissionDecision

        if not self._resource_enabled:
            return AdmissionDecision.ADMIT
        try:
            sample = self._resource_sampler.read()
            return self._resource_policy.evaluate(sample)
        except Exception as e:  # pragma: no cover — never crash the gateway to monitor it
            logger.warning(
                "AdmissionGate: resource policy failed (%s); admitting", e
            )
            return AdmissionDecision.ADMIT

    @staticmethod
    def _escalate(a, b):
        """Return the more restrictive of two decisions (REJECT > QUEUE > ADMIT)."""
        from praisonaiagents.gateway import AdmissionDecision

        rank = {
            AdmissionDecision.ADMIT: 0,
            AdmissionDecision.QUEUE: 1,
            AdmissionDecision.REJECT: 2,
        }
        return a if rank.get(a, 0) >= rank.get(b, 0) else b


def build_memory_pressure_policy(
    max_rss_mb: float = 0.0,
    soft_ratio: float = 0.9,
) -> Optional[object]:
    """Build a :class:`MemoryPressurePolicy` from a single ``max_rss_mb`` knob.

    Keeps the production surface to one number: the *hard* RSS ceiling above
    which turns are shed. The soft (queue/backpressure) threshold is derived as
    ``soft_ratio`` of the ceiling (90% by default) so a single flag/config value
    yields the full ADMIT/QUEUE/REJECT ladder without exposing three knobs.

    Returns ``None`` when no ceiling is configured (``max_rss_mb <= 0``), so
    admission stays concurrency-only and legacy behaviour is preserved.
    """
    try:
        hard = float(max_rss_mb or 0.0)
    except (TypeError, ValueError):
        return None
    if hard <= 0:
        return None
    try:
        from praisonaiagents.gateway import MemoryPressurePolicy
    except ImportError:  # pragma: no cover — core always present in wrapper
        return None
    soft = max(0.0, min(1.0, soft_ratio)) * hard
    return MemoryPressurePolicy(soft_rss_mb=soft, hard_rss_mb=hard)


def build_admission_gate(
    max_concurrent_runs: int = 0,
    queue_depth: int = 0,
    overflow_policy: str = "reject",
    policy: Optional[object] = None,
    resource_policy: Optional[object] = None,
) -> Optional[AdmissionGate]:
    """Construct an :class:`AdmissionGate` from config, or return ``None``.

    Returns ``None`` (no gate, legacy behaviour) when admission control is not
    configured — i.e. no explicit ``policy``/``resource_policy`` and
    ``max_concurrent_runs == 0``. A *negative* ``max_concurrent_runs`` is a
    misconfiguration (not "disabled") and is forwarded to
    :class:`ConcurrencyLimitPolicy`, which raises ``ValueError`` so startup
    fails fast instead of silently dropping the gate. Otherwise builds a
    :class:`ConcurrencyLimitPolicy` from the supplied config (unless an
    explicit ``policy`` is given) and wraps it in a gate.

    ``resource_policy`` (Issue #3445) wires an optional memory/resource-pressure
    policy (e.g. :class:`praisonaiagents.gateway.MemoryPressurePolicy`) into the
    gate so it queues under soft RSS pressure and sheds under hard pressure. A
    gate is built when *either* a concurrency ceiling *or* a resource policy is
    configured, so a memory-only deployment still gets backpressure.
    """
    if policy is None:
        # Only an explicit ``0`` (or ``None``) disables admission control. A
        # *negative* ceiling is a misconfiguration, not "disabled": fall through
        # to ``ConcurrencyLimitPolicy`` so it fails fast with a clear
        # ``ValueError`` instead of silently dropping overload protection.
        try:
            ceiling = int(max_concurrent_runs or 0)
        except (TypeError, ValueError):
            ceiling = -1  # non-int → let the policy raise the precise error
        no_ceiling = max_concurrent_runs in (None, 0, "0") or ceiling == 0
        if no_ceiling:
            # No concurrency ceiling: build a resource-only gate when a
            # resource policy is supplied, else no gate (legacy behaviour).
            if resource_policy is not None:
                return AdmissionGate(None, resource_policy=resource_policy)
            return None
        try:
            from praisonaiagents.gateway import ConcurrencyLimitPolicy
        except ImportError:  # pragma: no cover — core always present in wrapper
            return None
        policy = ConcurrencyLimitPolicy(
            max_concurrent_runs=max_concurrent_runs,
            queue_depth=queue_depth,
            overflow_policy=overflow_policy,
        )
    return AdmissionGate(policy, resource_policy=resource_policy)
