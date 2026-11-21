"""File-backed loops must distinguish empty input from read failures."""

import asyncio

import pytest

from praisonaiagents import StepResult, Workflow
from praisonaiagents.task.task import Task
from praisonaiagents.workflows import loop


@pytest.mark.parametrize("source", ["from_file", "from_csv"])
@pytest.mark.parametrize("async_run", [False, True], ids=["sync", "async"])
@pytest.mark.parametrize("kind", ["missing", "invalid_utf8"])
def test_loop_input_failure_is_not_empty_success(tmp_path, monkeypatch, source, async_run, kind):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    path = tmp_path / "input.txt"
    if kind == "invalid_utf8":
        path.write_bytes(b"\xff")
    seen = []
    task = Task(name="body", handler=lambda ctx: seen.append(ctx.variables["item"]) or StepResult(output="ok"))
    workflow = Workflow(steps=[loop(task, **{source: str(path)})])
    error = FileNotFoundError if kind == "missing" else UnicodeDecodeError

    with pytest.raises(error):
        if async_run:
            asyncio.run(workflow.astart("input"))
        else:
            workflow.start("input")
    assert seen == []


@pytest.mark.parametrize("source", ["from_file", "from_csv"])
def test_empty_file_is_a_valid_empty_loop(tmp_path, monkeypatch, source):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")
    seen = []
    task = Task(name="body", handler=lambda ctx: seen.append(ctx.variables["item"]) or StepResult(output="ok"))

    result = Workflow(steps=[loop(task, **{source: str(path)})]).start("input")

    assert result["status"] == "completed"
    assert seen == []
