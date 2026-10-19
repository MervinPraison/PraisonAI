"""Issue #5912: a turn parked on a human approval must not hold a run slot.

With ``max_concurrent_runs=1``, one turn waiting on a human approval used to
wedge every other turn. The admission gate now lends the slot back for the
duration of the approval wait and re-acquires it when the decision arrives.
"""

import asyncio
import contextvars
import threading

import pytest

from praisonai_bot.bots._admission import AdmissionGate
from praisonaiagents.approval.protocols import ApprovalDecision
from praisonaiagents.approval.registry import ApprovalRegistry
from praisonaiagents.gateway import ConcurrencyLimitPolicy


def _gate(max_runs=1):
    return AdmissionGate(
        ConcurrencyLimitPolicy(
            max_concurrent_runs=max_runs, queue_depth=4, overflow_policy="reject"
        )
    )


class _AsyncHuman:
    def __init__(self):
        self.parked = asyncio.Event()
        self.decide = asyncio.Event()

    async def request_approval(self, request):
        self.parked.set()
        await self.decide.wait()
        return ApprovalDecision(approved=True, reason="ok")


class _SyncHuman:
    def __init__(self):
        self.parked = threading.Event()
        self.decide = threading.Event()

    def request_approval_sync(self, request):
        self.parked.set()
        self.decide.wait(5)
        return ApprovalDecision(approved=True, reason="ok")

    async def request_approval(self, request):  # pragma: no cover - unused
        raise AssertionError("sync path expected")


def _registry(backend):
    reg = ApprovalRegistry()
    reg.set_backend(backend)
    return reg


@pytest.mark.asyncio
async def test_async_approval_wait_frees_slot():
    gate = _gate()
    human = _AsyncHuman()
    reg = _registry(human)

    async def parked_turn():
        async with gate.admit(session_id="a"):
            return await reg.approve_async("bot", "tool", {}, force=True)

    a = asyncio.ensure_future(parked_turn())
    await asyncio.wait_for(human.parked.wait(), 2)
    assert gate.in_flight == 0
    assert gate.stats()["awaiting_human"] == 1

    # Another session runs immediately — no queueing behind the human.
    ran = []
    async with gate.admit(session_id="b"):
        ran.append(gate.in_flight)
    assert ran == [1]

    human.decide.set()
    decision = await asyncio.wait_for(a, 2)
    assert decision.approved
    assert gate.in_flight == 0 and gate.awaiting_human == 0
    assert gate._sem._value == 1


@pytest.mark.asyncio
async def test_resumed_turn_reacquires_slot():
    gate = _gate()
    human = _AsyncHuman()
    reg = _registry(human)
    resumed = asyncio.Event()

    async def parked_turn():
        async with gate.admit(session_id="a"):
            await reg.approve_async("bot", "tool", {}, force=True)
            resumed.set()

    a = asyncio.ensure_future(parked_turn())
    await asyncio.wait_for(human.parked.wait(), 2)

    release_b = asyncio.Event()

    async def busy_turn():
        async with gate.admit(session_id="b"):
            await release_b.wait()

    b = asyncio.ensure_future(busy_turn())
    await asyncio.sleep(0)
    human.decide.set()
    await asyncio.sleep(0.05)
    # The approved turn waits for a slot instead of exceeding the ceiling.
    assert not resumed.is_set()
    assert gate.in_flight == 1

    release_b.set()
    await asyncio.wait_for(asyncio.gather(a, b), 2)
    assert resumed.is_set()
    assert gate.in_flight == 0 and gate._sem._value == 1


@pytest.mark.asyncio
async def test_sync_approval_in_worker_thread_frees_slot():
    gate = _gate()
    human = _SyncHuman()
    reg = _registry(human)
    loop = asyncio.get_running_loop()

    async def parked_turn():
        async with gate.admit(session_id="a"):
            return await loop.run_in_executor(
                None,
                contextvars.copy_context().run,
                lambda: reg.approve_sync("bot", "tool", {}, force=True),
            )

    a = asyncio.ensure_future(parked_turn())
    await loop.run_in_executor(None, human.parked.wait, 2)
    await asyncio.sleep(0.05)
    assert gate.in_flight == 0 and gate.awaiting_human == 1

    async with gate.admit(session_id="b"):
        assert gate.in_flight == 1

    human.decide.set()
    assert (await asyncio.wait_for(a, 2)).approved
    assert gate.in_flight == 0 and gate.awaiting_human == 0
    assert gate._sem._value == 1


@pytest.mark.asyncio
async def test_cancelled_while_parked_does_not_over_release():
    gate = _gate()
    human = _AsyncHuman()
    reg = _registry(human)

    async def parked_turn():
        async with gate.admit(session_id="a"):
            await reg.approve_async("bot", "tool", {}, force=True)

    a = asyncio.ensure_future(parked_turn())
    await asyncio.wait_for(human.parked.wait(), 2)
    a.cancel()
    with pytest.raises(asyncio.CancelledError):
        await a
    assert gate.in_flight == 0 and gate.awaiting_human == 0
    assert gate._sem._value == 1


@pytest.mark.asyncio
async def test_no_gate_bound_is_noop():
    human = _AsyncHuman()
    human.decide.set()
    reg = _registry(human)
    assert (await reg.approve_async("bot", "tool", {}, force=True)).approved
