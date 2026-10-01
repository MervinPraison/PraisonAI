"""Nested execution must honor Task gates, including cached pattern runs."""

import os

import pytest

from praisonaiagents import Task
from praisonaiagents.workflows.workflows import AgentFlow, Parallel


@pytest.mark.parametrize("cache", [False, True])
@pytest.mark.parametrize("nested", [False, True])
def test_nested_task_gate_is_rechecked(cache, nested):
    enabled = {"value": False}
    checks = []
    calls = []

    def gate(ctx):
        checks.append(enabled["value"])
        return enabled["value"]

    def handler(ctx):
        calls.append("run")
        return "done"

    step = Task(name="conditional", handler=handler, should_run=gate)
    pattern = Parallel(steps=[step])
    if nested:
        pattern = Parallel(steps=[pattern])
    flow = AgentFlow(steps=[pattern], cache=cache)
    flow.run("same", verbose=False)
    assert calls == []
    assert flow.step_statuses["conditional"] == "skipped"

    enabled["value"] = True
    flow.run("same", verbose=False)
    flow.run("same", verbose=False)
    enabled["value"] = False
    flow.run("same", verbose=False)
    assert checks == [False, True, True, False]
    assert calls == ["run"] * (1 if cache else 2)
    assert flow.step_statuses["conditional"] == "skipped"


@pytest.mark.skipif(
    os.getenv("RUN_REAL_KEY_TESTS") != "1" or not os.getenv("OPENAI_API_KEY"),
    reason="requires an explicitly enabled real test provider",
)
def test_nested_gate_with_real_agent():
    from praisonaiagents import Agent

    enabled = {"value": True}
    calls = []
    agent = Agent(name="nested", instructions="Answer briefly.",
                  llm=os.getenv("PRAISONAI_TEST_MODEL", "gpt-4o-mini"))

    def handler(ctx):
        calls.append("run")
        response = agent.start("Say hello in one short sentence.")
        print(response)
        assert response
        return response

    flow = AgentFlow(steps=[Parallel(steps=[Task(
        name="conditional", handler=handler,
        should_run=lambda ctx: enabled["value"],
    )])], cache=True)
    flow.run("same", verbose=False)
    flow.run("same", verbose=False)
    enabled["value"] = False
    flow.run("same", verbose=False)
    assert calls == ["run"]
    assert flow.step_statuses["conditional"] == "skipped"

