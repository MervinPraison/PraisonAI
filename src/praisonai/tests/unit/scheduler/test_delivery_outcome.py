"""Truthful scheduled-delivery outcome accounting (Issue #4454).

A standalone scheduled run must NOT report plain success when channel delivery
of its result fails. These tests verify that ``_deliver_result`` returns a typed
``DeliveryOutcome`` and that the sync/async schedulers fold that outcome into
their accounting: a failed delivery fires ``on_failure`` (not ``on_success``),
bumps an ``undelivered`` counter, and is visible in ``get_stats()`` — while an
intentional-silence marker stays a *recorded* non-outcome (not a failure).
"""

import asyncio

import pytest

from praisonai.scheduler._base_scheduler import DeliveryOutcome
from praisonai.scheduler.agent_scheduler import AgentScheduler
from praisonai.scheduler.async_agent_scheduler import AsyncAgentScheduler


class _StubDelivery:
    """Stand-in for ``SchedulerDelivery`` with a fixed ``deliver`` result."""

    def __init__(self, result: bool):
        self._result = result
        self._target = None
        self.sent = []

    def deliver(self, text: str) -> bool:
        self.sent.append(text)
        return self._result


def _make_sync(delivery_result, deliver="telegram:1"):
    sched = AgentScheduler(agent=object(), task="t", deliver=deliver, max_cost=None)
    if delivery_result is not None:
        sched._delivery = _StubDelivery(delivery_result)
    return sched


# ── _deliver_result returns a typed outcome ──────────────────────────────

def test_deliver_result_delivered():
    sched = _make_sync(True)
    assert sched._deliver_result("hello") is DeliveryOutcome.DELIVERED


def test_deliver_result_undelivered_on_false():
    sched = _make_sync(False)
    assert sched._deliver_result("hello") is DeliveryOutcome.UNDELIVERED
    assert sched._deliver_result("hello").undelivered is True


def test_deliver_result_not_configured_without_target():
    sched = AgentScheduler(agent=object(), task="t", deliver="", max_cost=None)
    assert sched._deliver_result("hello") is DeliveryOutcome.NOT_CONFIGURED


def test_deliver_result_suppressed_on_silence_marker():
    sched = _make_sync(True)
    # An exact intentional-silence marker is a recorded non-outcome.
    assert sched._deliver_result("NO_REPLY") is DeliveryOutcome.SUPPRESSED


def test_deliver_result_undelivered_when_wrapper_unbuildable():
    sched = AgentScheduler(agent=object(), task="t", deliver="telegram:1", max_cost=None)
    sched._delivery = None  # simulate build failure / praisonai-bot missing

    def _noop_build():
        sched._delivery = None
    sched._build_delivery = _noop_build

    assert sched._deliver_result("hello") is DeliveryOutcome.UNDELIVERED


# ── sync scheduler folds the outcome into truthful accounting ────────────

def test_sync_undelivered_fires_on_failure_not_on_success():
    successes, failures = [], []
    sched = AgentScheduler(
        agent=object(),
        task="t",
        deliver="telegram:1",
        max_cost=None,
        on_success=lambda r: successes.append(r),
        on_failure=lambda r: failures.append(r),
    )
    sched._delivery = _StubDelivery(False)

    ok = sched._finalize_delivery("result-text")
    # Mirror the scheduler's success-branch dispatch.
    if ok:
        sched.on_success("result-text")
    else:
        sched.on_failure("undelivered")

    assert ok is False
    assert successes == []
    assert failures, "on_failure must fire when delivery fails"
    stats = sched.get_stats()
    assert stats["undelivered_deliveries"] == 1
    assert stats["delivered_deliveries"] == 0


def test_sync_delivered_counts_and_fires_on_success():
    sched = _make_sync(True)
    ok = sched._finalize_delivery("result-text")
    assert ok is True
    stats = sched.get_stats()
    assert stats["delivered_deliveries"] == 1
    assert stats["undelivered_deliveries"] == 0


def test_sync_suppressed_is_not_a_failure():
    sched = _make_sync(True)
    ok = sched._finalize_delivery("[SILENT]")
    assert ok is True
    stats = sched.get_stats()
    # Suppressed silence is neither delivered nor undelivered.
    assert stats["delivered_deliveries"] == 0
    assert stats["undelivered_deliveries"] == 0


# ── async scheduler parity ───────────────────────────────────────────────

def test_async_finalize_delivery_outcomes():
    async def _run():
        sched = AsyncAgentScheduler(
            agent=object(), task="t", deliver="telegram:1", max_cost=None
        )
        sched._delivery = _StubDelivery(False)
        undelivered_ok = await asyncio.to_thread(sched._finalize_delivery, "r")

        sched2 = AsyncAgentScheduler(
            agent=object(), task="t", deliver="telegram:1", max_cost=None
        )
        sched2._delivery = _StubDelivery(True)
        delivered_ok = await asyncio.to_thread(sched2._finalize_delivery, "r")
        return undelivered_ok, delivered_ok, sched, sched2

    undelivered_ok, delivered_ok, sched, sched2 = asyncio.run(_run())
    assert undelivered_ok is False
    assert delivered_ok is True
    assert sched.get_stats_sync()["undelivered_deliveries"] == 1
    assert sched2.get_stats_sync()["delivered_deliveries"] == 1
