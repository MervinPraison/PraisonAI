"""Regression tests for issue #6303.

1. process="workflow" must not silently drop tasks past max_iter.
2. AgentTeam async fan-out must honour ConcurrencyRegistry limits.
"""
import asyncio

import pytest

from praisonaiagents import Agent, Task, AgentTeam
from praisonaiagents.agent.concurrency import get_concurrency_registry


def _stub_sync(monkeypatch):
    def ch(self, *a, **k):
        return "ok"
    monkeypatch.setattr(Agent, "chat", ch)
    monkeypatch.setattr(Agent, "start", ch)


@pytest.mark.parametrize("proc", ["sequential", "workflow"])
def test_workflow_runs_more_tasks_than_max_iter(monkeypatch, proc):
    _stub_sync(monkeypatch)
    ag = Agent(name="r", instructions="x", output="silent")
    tasks = [Task(name=f"t{i}", description="d", expected_output="o", agent=ag) for i in range(15)]
    AgentTeam(agents=[ag], tasks=tasks, process=proc, output="silent").start()
    assert all(t.status == "completed" for t in tasks)


def test_async_team_honours_concurrency_registry(monkeypatch):
    state = {"cur": 0, "peak": 0}

    async def fake(self, *a, **k):
        state["cur"] += 1
        state["peak"] = max(state["peak"], state["cur"])
        await asyncio.sleep(0.05)
        state["cur"] -= 1
        return "ok"

    for name in ("achat", "astart", "arun"):
        monkeypatch.setattr(Agent, name, fake)

    ag = Agent(name="researcher_6303", instructions="x", output="silent")
    registry = get_concurrency_registry()
    registry.set_limit("researcher_6303", 2)
    try:
        tasks = [
            Task(name=f"t{i}", description="d", expected_output="o", agent=ag, async_execution=True)
            for i in range(6)
        ]
        asyncio.run(AgentTeam(agents=[ag], tasks=tasks, process="workflow", output="silent").astart())
    finally:
        registry.remove_limit("researcher_6303")

    assert all(t.status == "completed" for t in tasks)
    assert state["peak"] == 2
