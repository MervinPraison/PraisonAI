"""tasks/cancel must stop background work and stay final (issue #5990)."""

import asyncio
import threading

import pytest

from praisonaiagents.ui.a2a.task_store import TaskStore
from praisonaiagents.ui.a2a.types import Message, Role, TextPart, TaskState


def _msg():
    return Message(message_id="m1", role=Role.USER, parts=[TextPart(text="hi")])


def test_terminal_states_are_final():
    store = TaskStore()
    t = store.create_task(_msg())
    store.update_status(t.id, TaskState.WORKING)
    store.cancel_task(t.id)
    store.update_status(t.id, TaskState.COMPLETED)
    assert store.get_task(t.id).status.state == TaskState.CANCELLED

    t2 = store.create_task(_msg())
    store.update_status(t2.id, TaskState.COMPLETED)
    store.cancel_task(t2.id)
    assert store.get_task(t2.id).status.state == TaskState.COMPLETED


def test_store_evicts_oldest_terminal_tasks(monkeypatch):
    from praisonaiagents.ui.a2a import task_store as ts
    monkeypatch.setattr(ts, "_MAX_TASKS", 3)
    store = TaskStore()
    done = store.create_task(_msg())
    store.update_status(done.id, TaskState.COMPLETED)
    live = [store.create_task(_msg()) for _ in range(3)]
    assert store.get_task(done.id) is None
    assert all(store.get_task(t.id) for t in live)


@pytest.mark.asyncio
async def test_cancel_stops_background_task_and_is_not_overwritten():
    from praisonaiagents import Agent
    from praisonaiagents.ui.a2a import A2A

    release = threading.Event()
    agent = Agent(name="Cancel Test", role="Tester", goal="Test")
    agent.chat = lambda _text: (release.wait(5), "late result")[1]
    a2a = A2A(agent=agent, url="http://localhost:8000/a2a")

    resp = await a2a._handle_message_send("1", {
        "message": {"messageId": "m1", "role": "user", "parts": [{"text": "Hi"}]},
        "configuration": {"returnImmediately": True},
    })
    import json
    task_id = json.loads(resp.body)["result"]["id"]
    await asyncio.sleep(0.05)
    running = a2a._running[task_id]

    a2a._handle_tasks_cancel("2", {"id": task_id})
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await running

    task = a2a.task_store.get_task(task_id)
    assert task.status.state == TaskState.CANCELLED
    assert not task.artifacts
    assert task_id not in a2a._running
