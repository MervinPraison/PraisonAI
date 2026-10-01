"""A cached step result must still respect its current execution gate."""

from praisonaiagents import Task
from praisonaiagents.workflows.workflows import AgentFlow


def test_cached_step_rechecks_gate_without_rerunning_handler():
    enabled = {"value": True}
    checks = []
    calls = []

    def should_run(ctx):
        checks.append(enabled["value"])
        return enabled["value"]

    def handler(ctx):
        calls.append("run")
        return "done"

    step = Task(name="conditional", handler=handler, should_run=should_run)
    flow = AgentFlow(steps=[step], cache=True)
    flow.run("same", verbose=False)
    flow.run("same", verbose=False)
    enabled["value"] = False
    skipped = flow.run("same", verbose=False)

    assert checks == [True, True, False]
    assert calls == ["run"]
    assert skipped["steps"] == []
    assert flow.step_statuses["conditional"] == "skipped"
    assert "conditional_output" not in skipped["variables"]

    enabled["value"] = True
    resumed = flow.run("same", verbose=False)
    assert checks == [True, True, False, True]
    assert calls == ["run"]
    assert resumed["output"] == "done"


def test_skipped_step_is_not_cached_when_gate_later_opens():
    enabled = {"value": False}
    calls = []
    step = Task(
        name="conditional", should_run=lambda ctx: enabled["value"],
        handler=lambda ctx: calls.append("run") or "done",
    )
    flow = AgentFlow(steps=[step], cache=True)
    assert flow.run("same", verbose=False)["steps"] == []
    enabled["value"] = True
    assert flow.run("same", verbose=False)["output"] == "done"
    assert calls == ["run"]
