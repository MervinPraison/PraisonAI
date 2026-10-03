"""Opt-in real-agent validation of cached conditional workflow execution."""

import os

import pytest


@pytest.mark.skipif(
    os.getenv("RUN_REAL_KEY_TESTS") != "1" or not os.getenv("OPENAI_API_KEY"),
    reason="requires an explicitly enabled real test provider",
)
def test_real_agent_cached_result_respects_current_condition():
    from praisonaiagents import Agent, Task
    from praisonaiagents.workflows.workflows import AgentFlow

    enabled = {"value": True}
    calls = []
    agent = Agent(
        name="conditional", instructions="Answer briefly.",
        llm=os.getenv("PRAISONAI_TEST_MODEL", "gpt-4o-mini"),
    )

    def handler(ctx):
        calls.append("run")
        response = agent.start("Say hello in one short sentence.")
        print(response)
        assert response
        return response

    flow = AgentFlow(steps=[Task(
        name="conditional", handler=handler,
        should_run=lambda ctx: enabled["value"],
    )], cache=True)
    flow.run("same", verbose=False)
    flow.run("same", verbose=False)
    enabled["value"] = False
    assert flow.run("same", verbose=False)["steps"] == []
    assert calls == ["run"]
