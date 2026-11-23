import asyncio

import pytest

from praisonaiagents.workflows import StepResult, Task, Workflow, repeat


@pytest.mark.parametrize("async_run", [False, True])
@pytest.mark.parametrize("nested", [False, True])
def test_repeat_normal_stop_keeps_output_and_stops_following_steps(async_run, nested):
    calls = []

    def stop(ctx):
        calls.append("stop")
        return StepResult(output="done", stop_workflow=True, variables={"answer": 42})

    def later(ctx):
        calls.append("later")
        return "later"

    body = repeat(stop, max_iterations=2) if nested else stop
    flow = Workflow(steps=[repeat([body, later], max_iterations=2), later])
    result = asyncio.run(flow.astart("input")) if async_run else flow.start("input")
    assert result["status"] == "completed"
    assert result["output"] == "done"
    assert result["variables"]["answer"] == 42
    assert calls == ["stop"]


@pytest.mark.parametrize("async_run", [False, True])
def test_repeat_error_stop_still_fails(async_run):
    calls = []

    def fail(ctx):
        calls.append("fail")
        raise ValueError("synthetic failure")

    def later(ctx):
        calls.append("later")
        return "later"

    flow = Workflow(steps=[repeat([Task(name="broken", handler=fail, on_error="stop", max_retries=0), later], max_iterations=2), later])
    result = asyncio.run(flow.astart("input")) if async_run else flow.start("input")
    assert result["status"] == "failed"
    assert result["output"] is None
    assert calls == ["fail"]


def test_repeat_replay_records_normal_stop_as_completed(monkeypatch):
    import praisonaiagents.workflows.workflows as workflows

    events = []
    monkeypatch.setattr(workflows, "_replay_step_begin", lambda *args, **kwargs: {})
    monkeypatch.setattr(workflows, "_replay_step_end", lambda span, status, output=None, *args, **kwargs: events.append((status, output)))
    def stop(ctx):
        return StepResult(output="done", stop_workflow=True)
    result = Workflow(steps=[repeat(stop, max_iterations=2)]).start("input")
    assert result["status"] == "completed"
    assert ("completed", "done") in events


def test_prior_nested_error_is_not_erased_by_normal_stop():
    def fail(ctx):
        raise ValueError("synthetic failure")

    def stop(ctx):
        return StepResult(output="done", stop_workflow=True)

    flow = Workflow(steps=[repeat([Task(name="broken", handler=fail, on_error="continue", max_retries=0), stop], max_iterations=1)])
    result = flow.start("input")
    assert result["status"] == "failed"
    assert result["output"] is None
