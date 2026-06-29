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
import logging
from contextlib import asynccontextmanager
from typing import Optional

logger = logging.getLogger(__name__)


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

    def __init__(self, policy: Optional[object]):
        self._policy = policy
        # Lazily-created so the gate can be constructed off the event loop
        # (e.g. during BotOS.__init__) and bound to whichever loop runs it.
        self._sem: Optional[asyncio.Semaphore] = None
        self._max = int(getattr(policy, "max_concurrent_runs", 0) or 0)
        self._queue_depth = int(getattr(policy, "queue_depth", 0) or 0)
        # Live counters.
        self._in_flight = 0
        self._queued = 0
        # Cumulative observability.
        self.admitted = 0
        self.rejected = 0
        self.shed = 0

    @property
    def enabled(self) -> bool:
        """Whether the gate enforces a ceiling (a positive ``max`` is set)."""
        return self._policy is not None and self._max > 0

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
        }

    def _ensure_sem(self) -> asyncio.Semaphore:
        if self._sem is None:
            self._sem = asyncio.Semaphore(self._max)
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
        if waited:
            self._queued += 1
        try:
            await sem.acquire()
        finally:
            if waited:
                self._queued -= 1

        self._in_flight += 1
        self.admitted += 1
        try:
            yield
        finally:
            self._in_flight -= 1
            sem.release()

    def _decide(self, *, session_id: str):
        from praisonaiagents.gateway import AdmissionDecision

        decide = getattr(self._policy, "decide", None)
        if decide is None:
            return AdmissionDecision.ADMIT
        try:
            return decide(
                in_flight=self._in_flight,
                queued=self._queued,
                session_id=session_id,
            )
        except Exception as e:  # pragma: no cover — defensive: never block on policy error
            logger.warning("AdmissionGate: policy.decide failed (%s); admitting", e)
            return AdmissionDecision.ADMIT


def build_admission_gate(
    max_concurrent_runs: int = 0,
    queue_depth: int = 0,
    overflow_policy: str = "reject",
    policy: Optional[object] = None,
) -> Optional[AdmissionGate]:
    """Construct an :class:`AdmissionGate` from config, or return ``None``.

    Returns ``None`` (no gate, legacy behaviour) when admission control is not
    configured — i.e. no explicit ``policy`` and ``max_concurrent_runs <= 0``.
    Otherwise builds a :class:`ConcurrencyLimitPolicy` from the supplied config
    (unless an explicit ``policy`` is given) and wraps it in a gate.
    """
    if policy is None:
        if not max_concurrent_runs or int(max_concurrent_runs) <= 0:
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
    return AdmissionGate(policy)
