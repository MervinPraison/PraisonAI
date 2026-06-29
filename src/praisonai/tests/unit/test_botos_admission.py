"""Unit tests for gateway inbound admission control (Issue #2454).

Verifies the wrapper-side ``AdmissionGate`` enforcement (concurrency ceiling +
bounded wait queue + overflow shed), its wiring into ``BotOS``, and that the
gate is a transparent no-op when admission control is not configured.
"""

import asyncio

import pytest

try:
    from praisonai.bots.botos import BotOS
    from praisonai.bots._admission import (
        AdmissionGate,
        AdmissionRejected,
        build_admission_gate,
    )
except ImportError:  # pragma: no cover - optional deps not installed
    BotOS = None

pytestmark = pytest.mark.skipif(
    BotOS is None, reason="praisonai bots not importable"
)


def test_disabled_by_default_no_gate():
    botos = BotOS()
    assert botos._admission_gate is None
    assert botos.admission_stats is None


def test_botos_builds_gate_from_config():
    botos = BotOS(max_concurrent_runs=8, queue_depth=16, overflow_policy="reject")
    assert botos._admission_gate is not None
    assert botos._admission_gate.enabled is True
    stats = botos.admission_stats
    assert stats["max_concurrent_runs"] == 8
    assert stats["queue_depth"] == 16


def test_build_admission_gate_returns_none_when_unconfigured():
    assert build_admission_gate(max_concurrent_runs=0) is None
    assert build_admission_gate() is None


def test_gate_disabled_is_transparent():
    async def main():
        gate = AdmissionGate(policy=None)
        assert gate.enabled is False
        async with gate.admit(session_id="u1"):
            return True

    assert asyncio.run(main()) is True


def test_gate_enforces_ceiling_and_rejects_overflow():
    async def main():
        gate = build_admission_gate(
            max_concurrent_runs=2, queue_depth=1, overflow_policy="reject"
        )
        release = asyncio.Event()
        rejected = []

        async def run(i):
            try:
                async with gate.admit(session_id=str(i)):
                    await release.wait()
            except AdmissionRejected as r:
                rejected.append(r.message)

        tasks = [asyncio.create_task(run(i)) for i in range(4)]
        await asyncio.sleep(0.05)
        # 2 admitted (in flight), 1 queued, 1 rejected (queue full).
        assert gate.in_flight == 2
        assert gate.queued == 1
        release.set()
        await asyncio.gather(*tasks)
        assert len(rejected) == 1
        assert gate.in_flight == 0
        assert gate.stats()["rejected"] == 1

    asyncio.run(main())


def test_shed_oldest_evicts_oldest_waiter():
    async def main():
        # ceiling=1, queue_depth=1, shed_oldest: 1 in-flight, 1 queued; a third
        # turn must evict the *oldest* waiter (not the newcomer, not unbounded).
        gate = build_admission_gate(
            max_concurrent_runs=1, queue_depth=1, overflow_policy="shed_oldest"
        )
        release = asyncio.Event()
        shed = []

        async def run(i):
            try:
                async with gate.admit(session_id=str(i)):
                    await release.wait()
            except AdmissionRejected as r:
                shed.append(i)

        t0 = asyncio.create_task(run(0))  # admitted, holds the slot
        await asyncio.sleep(0.02)
        t1 = asyncio.create_task(run(1))  # queued (oldest waiter)
        await asyncio.sleep(0.02)
        assert gate.in_flight == 1
        assert gate.queued == 1
        t2 = asyncio.create_task(run(2))  # newcomer evicts the oldest waiter
        await asyncio.sleep(0.02)
        # Oldest waiter (1) was shed; newcomer (2) took its queue slot. Queue
        # never grew past its depth, so shedding is bounded.
        assert shed == [1]
        assert gate.queued == 1
        assert gate.stats()["shed"] == 1
        release.set()
        await asyncio.gather(t0, t1, t2)
        assert gate.in_flight == 0

    asyncio.run(main())


def test_gate_releases_slot_on_exception():
    async def main():
        gate = build_admission_gate(max_concurrent_runs=1, queue_depth=0)

        async def boom():
            async with gate.admit(session_id="u"):
                raise RuntimeError("turn failed")

        with pytest.raises(RuntimeError):
            await boom()
        # Slot must be released even though the body raised.
        assert gate.in_flight == 0
        # A subsequent turn can still be admitted.
        async with gate.admit(session_id="u2"):
            assert gate.in_flight == 1

    asyncio.run(main())
