"""A cached step result must still respect its current execution gate."""

from praisonaiagents import Task
from praisonaiagents.workflows.workflows import AgentFlow
import pytest


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


def test_start_callback_prepares_context_before_cached_gate():
    enabled = {"value": True}
    starts = []
    calls = []

    def on_start(name, ctx):
        starts.append(enabled["value"])
        ctx.variables["allowed"] = enabled["value"]

    step = Task(
        name="conditional", should_run=lambda ctx: ctx.variables.get("allowed", False),
        handler=lambda ctx: calls.append("run") or "done",
    )
    flow = AgentFlow(steps=[step], cache=True, hooks={"on_step_start": on_start})
    assert flow.run("same", verbose=False)["output"] == "done"
    assert flow.run("same", verbose=False)["output"] == "done"
    enabled["value"] = False
    assert flow.run("same", verbose=False)["steps"] == []
    assert calls == ["run"]
    assert starts == [True, True, False]


@pytest.mark.parametrize("cache", [False, True])
def test_start_and_complete_hooks_pair_with_current_status(cache):
    enabled = {"value": True}
    events = []
    calls = []
    step = Task(
        name="conditional", should_run=lambda ctx: ctx.variables["allowed"],
        handler=lambda ctx: calls.append("run") or "done",
    )

    def on_start(name, ctx):
        events.append(("start", flow.step_statuses.get(name), step.status))
        ctx.variables["allowed"] = enabled["value"]

    def on_complete(name, result):
        events.append(("complete", flow.step_statuses[name], step.status, result.output))

    flow = AgentFlow(steps=[step], cache=cache, hooks={
        "on_step_start": on_start, "on_step_complete": on_complete,
    })
    for allowed in [True, True, False, True]:
        enabled["value"] = allowed
        result = flow.run("same", verbose=False)
        assert bool(result["steps"]) == allowed

    assert events == [
        ("start", "running", "running"),
        ("complete", "completed", "completed", "done"),
        ("start", "running", "running"),
        ("complete", "completed", "completed", "done"),
        ("start", "running", "running"),
        ("complete", "skipped", "skipped", ""),
        ("start", "running", "running"),
        ("complete", "completed", "completed", "done"),
    ]
    assert calls == (["run"] if cache else ["run"] * 3)


@pytest.mark.parametrize("allowed", [False, True])
def test_terminal_hook_failure_does_not_change_skip_or_cache_result(allowed):
    enabled = {"value": True}
    completions = []
    def on_complete(name, result):
        completions.append((name, result.output))
        raise RuntimeError("observer failed")

    flow = AgentFlow(steps=[Task(
        name="conditional", should_run=lambda ctx: enabled["value"],
        handler=lambda ctx: "done",
    )], cache=True, hooks={"on_step_complete": on_complete})
    flow.run("same", verbose=False)
    completions.clear()
    enabled["value"] = allowed
    result = flow.run("same", verbose=False)
    assert bool(result["steps"]) == allowed
    assert completions == [("conditional", "done" if allowed else "")]


@pytest.mark.parametrize("field", ["variables", "input", "previous_result"])
def test_hook_prepared_handler_inputs_change_cache_key(field):
    value = {"current": "first"}
    calls = []
    def prepare(name, context):
        if field == "variables":
            context.variables["prepared"] = value["current"]
        else:
            setattr(context, field, value["current"])
    def handler(context):
        result = context.variables["prepared"] if field == "variables" else getattr(context, field)
        calls.append(result)
        return result
    flow = AgentFlow(steps=[Task(name="prepared", handler=handler, should_run=lambda ctx: True)], cache=True,
                     hooks={"on_step_start": prepare})
    assert flow.run("same", verbose=False)["output"] == "first"
    value["current"] = "second"
    assert flow.run("same", verbose=False)["output"] == "second"
    assert flow.run("same", verbose=False)["output"] == "second"
    assert calls == ["first", "second"]


def test_completion_result_distinguishes_skip_from_empty_handler_output():
    enabled = {"value": False}
    outcomes = []
    flow = AgentFlow(steps=[Task(name="empty", handler=lambda ctx: "", should_run=lambda ctx: enabled["value"])],
                     hooks={"on_step_complete": lambda name, result: outcomes.append((result.output, result.skipped))})
    flow.run("same", verbose=False)
    enabled["value"] = True
    flow.run("same", verbose=False)
    assert outcomes == [("", True), ("", False)]


def test_agent_cache_uses_actual_prompt_variables_after_hook_clears_context():
    from types import SimpleNamespace

    prompts = []
    agent = SimpleNamespace(name="echo", chat=lambda prompt, **kwargs: prompts.append(prompt) or prompt)
    step = Task(name="agent", agent=agent, action="{{token}}")
    flow = AgentFlow(steps=[step], cache=True,
                     hooks={"on_step_start": lambda name, ctx: ctx.variables.clear()})
    flow.variables["token"] = "first"
    assert flow.run("same", verbose=False)["output"] == "first"
    flow.variables["token"] = "second"
    assert flow.run("same", verbose=False)["output"] == "second"
    assert flow.run("same", verbose=False)["output"] == "second"
    assert prompts == ["first", "second"]


@pytest.mark.parametrize("stop", [False, True])
def test_cached_completion_preserves_handler_stop_signal(stop):
    from praisonaiagents.workflows.workflows import StepResult

    calls = []
    completions = []
    downstream = []

    def handler(context):
        calls.append("run")
        return StepResult(output="done", stop_workflow=stop)

    flow = AgentFlow(steps=[
        Task(name="first", handler=handler),
        Task(name="next", handler=lambda ctx: downstream.append("run") or "next"),
    ], cache=True, hooks={
        "on_step_complete": lambda name, result: completions.append(
            (name, result.output, result.stop_workflow)
        ),
    })
    flow.run("same", verbose=False)
    first_completions = list(completions)
    completions.clear()
    flow.run("same", verbose=False)

    assert calls == ["run"]
    assert completions == first_completions
    assert completions[0] == ("first", "done", stop)
    assert downstream == ([] if stop else ["run"])
