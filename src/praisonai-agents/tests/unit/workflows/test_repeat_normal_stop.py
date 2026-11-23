import asyncio

import pytest

from praisonaiagents.workflows import Discussion, StepResult, Task, Workflow, loop, parallel, repeat, route, when


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


@pytest.mark.parametrize("async_run", [False, True])
@pytest.mark.parametrize("nest", ["direct", "repeat", "if", "repeat_outer"])
def test_conditional_normal_stop_preserves_outcome(async_run, nest):
    calls = []

    def stop(ctx):
        calls.append("stop")
        return StepResult(output="done", stop_workflow=True, variables={"answer": 42})

    def later(ctx):
        calls.append("later")
        return "later"

    body = repeat(stop, max_iterations=2) if nest == "repeat" else stop
    if nest == "if":
        body = when("true", [body])
    branch = when("true", [body, later])
    if nest == "repeat_outer":
        branch = repeat(branch, max_iterations=2)
    flow = Workflow(steps=[branch, later])
    result = asyncio.run(flow.astart("input")) if async_run else flow.start("input")
    assert result["status"] == "completed"
    assert result["output"] == "done"
    assert result["variables"]["answer"] == 42
    assert calls == ["stop"]


@pytest.mark.parametrize("async_run", [False, True])
def test_conditional_error_stop_still_fails(async_run):
    calls = []

    def fail(ctx):
        calls.append("fail")
        raise ValueError("synthetic failure")

    def later(ctx):
        calls.append("later")
        return "later"

    flow = Workflow(steps=[when("true", [Task(name="broken", handler=fail, on_error="stop", max_retries=0), later]), later])
    result = asyncio.run(flow.astart("input")) if async_run else flow.start("input")
    assert result["status"] == "failed"
    assert result["output"] is None
    assert calls == ["fail"]


def test_conditional_prior_error_is_not_erased_by_normal_stop():
    def fail(ctx):
        raise ValueError("synthetic failure")

    def stop(ctx):
        return StepResult(output="done", stop_workflow=True)

    flow = Workflow(steps=[when("true", [Task(name="broken", handler=fail, on_error="continue", max_retries=0), stop])])
    result = flow.start("input")
    assert result["status"] == "failed"
    assert result["output"] is None


@pytest.mark.parametrize("failure", [False, True])
def test_conditional_replay_records_stop_status(monkeypatch, failure):
    import praisonaiagents.workflows.workflows as workflows

    events = []
    monkeypatch.setattr(workflows, "_replay_step_begin", lambda *args, **kwargs: {})
    monkeypatch.setattr(workflows, "_replay_step_end", lambda span, status, output=None, *args, **kwargs: events.append((status, output)))

    def handler(ctx):
        if failure:
            raise ValueError("synthetic failure")
        return StepResult(output="done", stop_workflow=True)

    step = Task(name="handler", handler=handler, on_error="stop", max_retries=0)
    result = Workflow(steps=[when("true", [step])]).start("input")
    assert result["status"] == ("failed" if failure else "completed")
    assert ("failed", None) in events if failure else ("completed", "done") in events


@pytest.mark.parametrize("async_run", [False, True])
@pytest.mark.parametrize("nest", ["direct", "repeat", "if", "outer_repeat"])
def test_route_normal_stop_preserves_outcome(async_run, nest):
    calls = []

    def choose(ctx):
        return "go"

    def stop(ctx):
        calls.append("stop")
        return StepResult(output="done", stop_workflow=True, variables={"answer": 42})

    def later(ctx):
        calls.append("later")
        return "later"

    body = repeat(stop, max_iterations=2) if nest == "repeat" else when("true", [stop]) if nest == "if" else stop
    branch = route({"go": [body, later]})
    if nest == "outer_repeat":
        branch = repeat(branch, max_iterations=2)
    flow = Workflow(steps=[choose, branch, later])
    result = asyncio.run(flow.astart("input")) if async_run else flow.start("input")
    assert result["status"] == "completed"
    assert result["output"] == "done"
    assert result["variables"]["answer"] == 42
    assert calls == ["stop"]


@pytest.mark.parametrize("async_run", [False, True])
def test_route_error_stop_still_fails(async_run):
    calls = []

    def fail(ctx):
        calls.append("fail")
        raise ValueError("synthetic failure")

    def later(ctx):
        calls.append("later")
        return "later"

    flow = Workflow(steps=[lambda ctx: "go", route({"go": [Task(name="broken", handler=fail, on_error="stop", max_retries=0), later]}), later])
    result = asyncio.run(flow.astart("input")) if async_run else flow.start("input")
    assert result["status"] == "failed"
    assert result["output"] is None
    assert calls == ["fail"]


def test_route_prior_error_is_not_erased_by_normal_stop():
    def fail(ctx):
        raise ValueError("synthetic failure")

    def stop(ctx):
        return StepResult(output="done", stop_workflow=True)

    flow = Workflow(steps=[lambda ctx: "go", route({"go": [Task(name="broken", handler=fail, on_error="continue", max_retries=0), stop]})])
    result = flow.start("input")
    assert result["status"] == "failed"
    assert result["output"] is None


@pytest.mark.parametrize("failure", [False, True])
def test_route_replay_records_stop_status(monkeypatch, failure):
    import praisonaiagents.workflows.workflows as workflows

    events = []
    monkeypatch.setattr(workflows, "_replay_step_begin", lambda *args, **kwargs: {})
    monkeypatch.setattr(workflows, "_replay_step_end", lambda span, status, output=None, *args, **kwargs: events.append((status, output)))

    def handler(ctx):
        if failure:
            raise ValueError("synthetic failure")
        return StepResult(output="done", stop_workflow=True)

    step = Task(name="handler", handler=handler, on_error="stop", max_retries=0)
    result = Workflow(steps=[lambda ctx: "go", route({"go": [step]})]).start("input")
    assert result["status"] == ("failed" if failure else "completed")
    assert any(status == ("failed" if failure else "completed") and (failure or output == "done") for status, output in events)


@pytest.mark.parametrize("async_run", [False, True])
@pytest.mark.parametrize("nest", ["direct", "repeat", "if"])
def test_sequential_loop_normal_stop(async_run, nest):
    calls = []

    def stop(ctx):
        calls.append(ctx.variables["item"])
        return StepResult(output="done", stop_workflow=True, variables={"answer": 42})

    def later(ctx):
        calls.append("later")
        return "later"

    body = repeat(stop, max_iterations=2) if nest == "repeat" else when("true", [stop]) if nest == "if" else stop
    flow = Workflow(steps=[loop(body, over="items"), later], variables={"items": ["a", "b"]})
    result = asyncio.run(flow.astart("input")) if async_run else flow.start("input")
    assert result["status"] == "completed"
    assert result["output"] == "done"
    assert result["variables"]["loop_outputs"] == ["done"]
    assert result["variables"]["answer"] == 42
    assert "item" not in result["variables"]
    assert calls == ["a"]


@pytest.mark.parametrize("failure", [False, True])
@pytest.mark.parametrize("async_run", [False, True])
def test_parallel_loop_stop_preserves_order_and_failures(async_run, failure):
    from threading import Barrier

    barrier = Barrier(2, timeout=5)
    calls = []

    def step(ctx):
        item = ctx.variables["item"]
        calls.append(item)
        barrier.wait()
        if failure and item == "b":
            raise ValueError("synthetic failure")
        return StepResult(output=item, stop_workflow=True, variables={"answer": item})

    def later(ctx):
        calls.append("later")
        return "later"

    task = Task(name="step", handler=step, on_error="stop", max_retries=0)
    flow = Workflow(steps=[loop(task, over="items", parallel=True, max_workers=2), later], variables={"items": ["a", "b"]})
    result = asyncio.run(flow.astart("input")) if async_run else flow.start("input")
    assert result["status"] == ("failed" if failure else "completed")
    assert result["output"] == (None if failure else "a\nb")
    assert result["variables"]["loop_outputs"] == (["a", None] if failure else ["a", "b"])
    assert result["variables"]["answer"] == ("a" if failure else "b")
    assert "item" not in result["variables"]
    assert sorted(calls) == ["a", "b"]


@pytest.mark.parametrize("async_run", [False, True])
def test_loop_error_stops_remaining_iterations(async_run):
    calls = []

    def fail(ctx):
        calls.append(ctx.variables["item"])
        raise ValueError("synthetic failure")

    task = Task(name="broken", handler=fail, on_error="stop", max_retries=0)
    flow = Workflow(steps=[loop(task, over="items")], variables={"items": ["a", "b"]})
    result = asyncio.run(flow.astart("input")) if async_run else flow.start("input")
    assert result["status"] == "failed"
    assert result["output"] is None
    assert calls == ["a"]


def test_loop_normal_stop_inside_repeat():
    def stop(ctx):
        return StepResult(output="done", stop_workflow=True)

    flow = Workflow(steps=[repeat(loop(stop, over="items"), max_iterations=2)], variables={"items": ["a", "b"]})
    result = flow.start("input")
    assert result["status"] == "completed"
    assert result["output"] == "done"
    assert result["variables"]["loop_outputs"] == ["done"]


@pytest.mark.parametrize("failure", [False, True])
def test_loop_replay_records_stop_status(monkeypatch, failure):
    import praisonaiagents.workflows.workflows as workflows

    events = []
    monkeypatch.setattr(workflows, "_replay_step_begin", lambda *args, **kwargs: {})
    monkeypatch.setattr(workflows, "_replay_step_end", lambda span, status, output=None, *args, **kwargs: events.append((status, output)))

    def step(ctx):
        if failure:
            raise ValueError("synthetic failure")
        return StepResult(output="done", stop_workflow=True)

    task = Task(name="step", handler=step, on_error="stop", max_retries=0)
    result = Workflow(steps=[loop(task, over="items")], variables={"items": ["a"]}).start("input")
    assert result["status"] == ("failed" if failure else "completed")
    assert any(status == ("failed" if failure else "completed") and (failure or output == "done") for status, output in events)


@pytest.mark.parametrize("async_run", [False, True])
@pytest.mark.parametrize("nested", [False, True])
def test_discussion_normal_stop_preserves_transcript(async_run, nested):
    calls = []

    def stop(ctx):
        calls.append("stop")
        return StepResult(output="done", stop_workflow=True)

    def later(ctx):
        calls.append("later")
        return "later"

    discussion = Discussion([stop, later], rounds=2)
    body = repeat(discussion, max_iterations=2) if nested else discussion
    flow = Workflow(steps=[body, later])
    result = asyncio.run(flow.astart("input")) if async_run else flow.start("input")
    assert result["status"] == "completed"
    assert result["output"] == "done"
    assert result["variables"]["discussion_transcript"] == "stop: done"
    assert calls == ["stop"]


@pytest.mark.parametrize("async_run", [False, True])
@pytest.mark.parametrize("failure", [False, True])
def test_parallel_stop_keeps_concurrent_order_and_failures(async_run, failure):
    from threading import Barrier

    barrier = Barrier(2, timeout=5)
    calls = []

    def stop(ctx):
        calls.append("stop")
        barrier.wait()
        return StepResult(output="done", stop_workflow=True)

    def peer(ctx):
        calls.append("peer")
        barrier.wait()
        if failure:
            raise ValueError("synthetic failure")
        return "peer"

    def later(ctx):
        calls.append("later")
        return "later"

    task = Task(name="peer", handler=peer, on_error="stop", max_retries=0)
    flow = Workflow(steps=[parallel([stop, task], max_workers=2), later])
    result = asyncio.run(flow.astart("input")) if async_run else flow.start("input")
    assert result["status"] == ("failed" if failure else "completed")
    assert result["output"] == (None if failure else "done\n---\npeer")
    assert result["variables"]["parallel_outputs"] == (["done", None] if failure else ["done", "peer"])
    assert sorted(calls) == ["peer", "stop"]


@pytest.mark.parametrize("pattern", ["parallel", "discussion"])
@pytest.mark.parametrize("failure", [False, True])
def test_remaining_pattern_replay_stop_status(monkeypatch, pattern, failure):
    import praisonaiagents.workflows.workflows as workflows

    events = []
    monkeypatch.setattr(workflows, "_replay_step_begin", lambda *args, **kwargs: {})
    monkeypatch.setattr(workflows, "_replay_step_end", lambda span, status, output=None, *args, **kwargs: events.append((status, output)))

    def handler(ctx):
        if failure:
            raise ValueError("synthetic failure")
        return StepResult(output="done", stop_workflow=True)

    task = Task(name="handler", handler=handler, on_error="stop", max_retries=0)
    body = parallel([task]) if pattern == "parallel" else Discussion([task], rounds=1)
    result = Workflow(steps=[body]).start("input")
    assert result["status"] == ("failed" if failure else "completed")
    assert any(status == ("failed" if failure else "completed") and (failure or output == "done") for status, output in events)
