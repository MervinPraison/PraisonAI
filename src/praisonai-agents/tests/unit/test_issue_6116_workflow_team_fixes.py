"""Regression tests for issue #6116 (offline, no LLM calls)."""
import asyncio

import pytest

from praisonaiagents import Agent, AgentTeam, StepResult, Task, Workflow
from praisonaiagents.workflows import loop, parallel
from praisonaiagents.workflows.workflows import WorkflowStepError


async def _fetch(ctx):
    await asyncio.sleep(0)
    return StepResult(output="real result")


def _use(ctx):
    return StepResult(output=f"next saw: {ctx.previous_result}")


def test_async_handler_awaited_in_start():
    r = Workflow(steps=[_fetch, _use]).start("x")
    assert r["status"] == "completed"
    assert r["output"] == "next saw: real result"


def test_async_handler_awaited_in_astart():
    r = asyncio.run(Workflow(steps=[_fetch, _use]).astart("x"))
    assert r["status"] == "completed"
    assert r["output"] == "next saw: real result"


def test_failed_parallel_branch_error_surfaces():
    def ok(ctx):
        return StepResult(output="a")

    def bad(ctx):
        raise KeyError("missing")

    r = Workflow(steps=[parallel([ok, bad]), ok]).start("x")
    assert r["status"] == "failed"
    assert "missing" in r["error"]
    assert r["output"] is None


def test_failed_run_does_not_expose_previous_output():
    def prep(ctx):
        return StepResult(output="x")

    def boom(ctx):
        raise ValueError("bad input")

    r = Workflow(steps=[prep, boom]).start("go")
    assert r["status"] == "failed"
    assert r["output"] is None
    assert "bad input" in r["error"]


def test_loop_over_missing_variable_fails_loudly():
    def body(ctx):
        return StepResult(output="b")

    with pytest.raises(WorkflowStepError, match="itmes"):
        Workflow(steps=[loop(body, over="itmes")]).start("x")


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    return Agent(name="a", instructions="x", llm="gpt-4o-mini")


def _task(name, agent, **kw):
    return Task(name=name, description="d", expected_output="o", agent=agent, **kw)


def test_team_keeps_user_declared_routing(agent):
    a = _task("A", agent, next_tasks=["C"])
    b = _task("B", agent)
    c = _task("C", agent)
    AgentTeam(agents=[agent], tasks=[a, b, c])
    assert a.next_tasks == ["C"]
    assert not b.context


def test_team_keeps_async_fan_out_independent(agent):
    r1 = _task("r1", agent, async_execution=True)
    r2 = _task("r2", agent, async_execution=True)
    final = _task("final", agent, context=[r1, r2])
    AgentTeam(agents=[agent], tasks=[r1, r2, final])
    assert not r2.context
    assert [t.name for t in final.context] == ["r1", "r2"]


def test_team_chain_is_idempotent(agent):
    t1 = _task("t1", agent)
    t2 = _task("t2", agent)
    for _ in range(3):
        AgentTeam(agents=[agent], tasks=[t1, t2])
    assert t1.next_tasks == ["t2"]
    assert [t.name for t in t2.context] == ["t1"]
