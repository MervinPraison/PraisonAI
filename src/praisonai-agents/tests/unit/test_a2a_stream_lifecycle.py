"""Tests for A2A message/stream lifecycle (issue #6151)."""
import asyncio
import time

import pytest

from praisonaiagents.ui.a2a.streaming import stream_agent_response
from praisonaiagents.ui.a2a.task_store import TaskStore
from praisonaiagents.ui.a2a.types import Message, Role, TaskState, TextPart


@pytest.fixture(autouse=True)
def _restore_event_loop():
    # asyncio.run() leaves no current loop; later tests using
    # get_event_loop() would break.
    yield
    asyncio.set_event_loop(asyncio.new_event_loop())


def _new_task(store):
    msg = Message(message_id="m1", role=Role.USER, parts=[TextPart(text="hi")])
    return store.create_task(msg)


async def _consume(agen):
    return [e async for e in agen]


class _Slow:
    def chat(self, x):
        time.sleep(0.5)
        return "done"


class _Team:
    def start(self, x):
        return f"team:{x}"


class _Boom:
    def chat(self, x):
        raise ValueError("kaboom")


def test_stream_does_not_block_event_loop():
    async def main():
        ticks = 0

        async def heartbeat():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.02)
                ticks += 1

        hb = asyncio.create_task(heartbeat())
        t = time.time()
        await asyncio.gather(
            _consume(stream_agent_response(_Slow(), "hi", "a")),
            _consume(stream_agent_response(_Slow(), "hi", "b")),
        )
        elapsed = time.time() - t
        hb.cancel()
        return elapsed, ticks

    elapsed, ticks = asyncio.run(main())
    assert elapsed < 0.9
    assert ticks > 5


def test_stream_updates_task_store_and_supports_team():
    store = TaskStore()
    task = _new_task(store)
    running = {}
    events = asyncio.run(_consume(stream_agent_response(
        _Team(), "x", task.id, task_store=store, running=running)))
    assert any("team:x" in e for e in events)
    assert any('"completed"' in e for e in events)
    t = store.get_task(task.id)
    assert t.status.state == TaskState.COMPLETED
    assert t.artifacts and running == {}
    assert task.id not in store._pinned


def test_stream_failure_reports_reason():
    store = TaskStore()
    task = _new_task(store)
    events = asyncio.run(_consume(stream_agent_response(
        _Boom(), "x", task.id, task_store=store)))
    final = [e for e in events if '"failed"' in e]
    assert final and "kaboom" in final[0]
    assert store.get_task(task.id).status.state == TaskState.FAILED


def test_stream_cancel_via_running_handle():
    store = TaskStore()
    task = _new_task(store)
    running = {}

    async def main():
        consumer = asyncio.create_task(_consume(stream_agent_response(
            _Slow(), "x", task.id, task_store=store, running=running)))
        while task.id not in running:
            await asyncio.sleep(0.01)
        # Mirrors tasks/cancel: mark cancelled, then cancel the handle
        store.cancel_task(task.id)
        running[task.id].cancel()
        return await consumer

    events = asyncio.run(main())
    assert any('"canceled"' in e or '"cancelled"' in e for e in events)
    assert store.get_task(task.id).status.state == TaskState.CANCELLED
    assert running == {}


class _Counting:
    calls = 0

    def chat(self, x):
        _Counting.calls += 1
        return "ran"


def test_cancel_before_call_registered_skips_agent():
    store = TaskStore()
    task = _new_task(store)
    running = {}

    async def main():
        agen = stream_agent_response(
            _Counting(), "x", task.id, task_store=store, running=running)
        first = await agen.__anext__()
        assert '"working"' in first
        # tasks/cancel arrives before the call is registered
        store.cancel_task(task.id)
        return [first] + [e async for e in agen]

    events = asyncio.run(main())
    assert _Counting.calls == 0
    assert not any('"completed"' in e for e in events)
    assert store.get_task(task.id).status.state == TaskState.CANCELLED
    assert running == {} and task.id not in store._pinned


def test_early_close_leaves_terminal_state_and_unpins():
    store = TaskStore()
    task = _new_task(store)

    async def main():
        agen = stream_agent_response(_Team(), "x", task.id, task_store=store)
        await agen.__anext__()
        await agen.aclose()

    asyncio.run(main())
    assert store.get_task(task.id).status.state == TaskState.CANCELLED
    assert task.id not in store._pinned
