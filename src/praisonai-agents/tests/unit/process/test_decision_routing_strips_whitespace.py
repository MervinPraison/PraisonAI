"""A decision string with surrounding whitespace must route like a clean one.

`process.py` derives the routing key as `current_task.result.raw.lower()` -- eight
sites, none of which `.strip()`. `result.raw` is raw model text, which routinely
carries a trailing newline. The condition lookup then misses, and a miss is
treated as "exit condition met": the workflow finishes silently, the rejected
task is never retried, no feedback is produced, and no exception is raised.

`run_outcome.validate_decision_string` -- the typed classifier the same code path
calls -- does `.lower().strip()`, so the two disagree about the same string.
"""
import asyncio

import pytest

from praisonaiagents import Task, TaskOutput
from praisonaiagents.process import Process
from praisonaiagents.run_outcome import validate_decision_string


class _ScriptedAgent:
    """Returns a fixed string. No LLM, no network."""

    def __init__(self, name, out):
        self.name = name
        self.out = out
        self.role = "r"
        self.goal = "g"
        self.tools = []
        self.llm = "gpt-4o-mini"

    def execute_task(self, task, context=None, **kw):
        return self.out

    async def aexecute_task(self, task, context=None, **kw):
        return self.out


def _run(decision_text, limit=25):
    """Drive the real workflow to natural completion; return (visited, collect task).

    `limit` is a runaway guard only. This workflow self-terminates after 10 task
    visits, so the guard must sit above that -- breaking out at exactly 10 cuts the
    generator off before its final step and the clean-decision control fails for
    the harness's reasons rather than the code's.
    """
    collect = _ScriptedAgent("collector", "Collected only 3 items")
    judge = _ScriptedAgent("judge", decision_text)

    t1 = Task(name="collect_data", description="Collect data", expected_output="Data",
              agent=collect, is_start=True, next_tasks=["validate_data"])
    t2 = Task(name="validate_data", description="Validate", expected_output="verdict",
              agent=judge, task_type="decision",
              condition={"valid": [], "invalid": ["collect_data"]})
    t2.previous_tasks = ["collect_data"]

    process = Process(agents={"collector": collect, "judge": judge},
                      tasks={t1.id: t1, t2.id: t2}, verbose=0)

    visited = []

    async def drive():
        async for tid in process.aworkflow():
            task = process.tasks[tid]
            visited.append(task.name)
            task.result = TaskOutput(description="d", raw=task.agent.out,
                                     agent=task.agent.name)
            task.status = "completed"
            if len(visited) >= limit:
                break

    asyncio.run(drive())
    return visited, t1


def _run_sync(decision_text, limit=25):
    """Same scenario against the synchronous ``workflow()`` generator.

    ``workflow()`` is a separately duplicated code path from ``aworkflow()`` --
    its routing sites were edited independently -- so it needs its own
    regression coverage. A whitespace regression in only one of the two paths
    would otherwise leave this suite green.
    """
    collect = _ScriptedAgent("collector", "Collected only 3 items")
    judge = _ScriptedAgent("judge", decision_text)

    t1 = Task(name="collect_data", description="Collect data", expected_output="Data",
              agent=collect, is_start=True, next_tasks=["validate_data"])
    t2 = Task(name="validate_data", description="Validate", expected_output="verdict",
              agent=judge, task_type="decision",
              condition={"valid": [], "invalid": ["collect_data"]})
    t2.previous_tasks = ["collect_data"]

    process = Process(agents={"collector": collect, "judge": judge},
                      tasks={t1.id: t1, t2.id: t2}, verbose=0)

    visited = []
    for tid in process.workflow():
        task = process.tasks[tid]
        visited.append(task.name)
        task.result = TaskOutput(description="d", raw=task.agent.out,
                                 agent=task.agent.name)
        task.status = "completed"
        if len(visited) >= limit:
            break
    return visited, t1


@pytest.mark.parametrize("decision", ["invalid", "invalid\n", " invalid", "invalid  ",
                                      "\ninvalid\n"])
def test_rejected_output_is_retried_regardless_of_whitespace(decision):
    visited, collect_task = _run(decision)
    assert visited.count("collect_data") > 1, (
        f"judge returned {decision!r} (a rejection) but collect_data was never "
        f"retried; workflow ran {visited} and finished silently")


@pytest.mark.parametrize("decision", ["invalid\n", " invalid"])
def test_validation_feedback_survives_whitespace(decision):
    _visited, collect_task = _run(decision)
    assert collect_task.validation_feedback is not None, (
        f"judge returned {decision!r} but the retried task got no feedback about "
        f"what was wrong")


@pytest.mark.parametrize("decision", ["invalid\n", " invalid", "invalid  "])
def test_router_and_typed_classifier_agree(decision):
    """The routing key and the typed classifier must read the same string the same way."""
    routing_key = decision.lower().strip()
    assert validate_decision_string(decision) == validate_decision_string(routing_key)
    assert routing_key in Process.VALIDATION_FAILURE_DECISIONS, (
        f"{decision!r} classifies as {validate_decision_string(decision)!r} but its "
        f"routing key {routing_key!r} is not recognised as a failure decision")


def test_clean_decision_still_works():
    """Control: the unpadded spelling must keep behaving exactly as before."""
    visited, collect_task = _run("invalid")
    assert visited.count("collect_data") > 1
    assert collect_task.validation_feedback is not None


@pytest.mark.parametrize("decision", ["invalid", "invalid\n", " invalid", "invalid  ",
                                      "\ninvalid\n"])
def test_sync_rejected_output_is_retried_regardless_of_whitespace(decision):
    """The synchronous ``workflow()`` path must strip routing keys too."""
    visited, _collect_task = _run_sync(decision)
    assert visited.count("collect_data") > 1, (
        f"sync judge returned {decision!r} (a rejection) but collect_data was "
        f"never retried; workflow ran {visited} and finished silently")


def test_sync_clean_decision_still_works():
    """Control for the synchronous path."""
    visited, _collect_task = _run_sync("invalid")
    assert visited.count("collect_data") > 1
