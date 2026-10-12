"""Task and Workflow step output_file writes must stay inside the project root."""

import asyncio
import os

import pytest
from praisonaiagents import (
    Agent,
    AgentTeam,
    StepResult,
    Task,
    Workflow,
    WorkflowContext,
)


@pytest.fixture
def root(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.delenv("PRAISONAI_PROJECT_ROOT", raising=False)
    return work


def _team(output_file, create_directory=True):
    agent = Agent(name="a", instructions="test")
    task = Task(
        description="d",
        expected_output="e",
        agent=agent,
        output_file=output_file,
        create_directory=create_directory,
    )
    return AgentTeam(agents=[agent], tasks=[task]), task


def _workflow(output_file):
    def generate(ctx: WorkflowContext) -> StepResult:
        return StepResult(output="report")

    return Workflow(steps=[Task(name="gen", handler=generate, output_file=output_file)])


def test_task_output_file_traversal_blocked(root):
    team, task = _team("../escaped/out.txt")
    team.save_output_to_file(task, "PWNED")
    assert not (root.parent / "escaped").exists()


def test_task_output_file_symlink_escape_blocked(root, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, root / "link")
    team, task = _team("link/out.txt")
    team.save_output_to_file(task, "PWNED")
    assert not (outside / "out.txt").exists()


def test_task_output_file_inside_root(root):
    team, task = _team("sub/out.txt")
    team.save_output_to_file(task, "héllo 世界")
    assert (root / "sub" / "out.txt").read_text(encoding="utf-8") == "héllo 世界"

    team, task = _team(str(root / "abs.txt"))
    team.save_output_to_file(task, "ok")
    assert (root / "abs.txt").read_text() == "ok"


def test_task_output_file_respects_create_directory(root):
    team, task = _team("missing/out.txt", create_directory=False)
    team.save_output_to_file(task, "ok")
    assert not (root / "missing").exists()


def test_task_output_file_project_root_override(root, tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_PROJECT_ROOT", str(tmp_path))
    team, task = _team(str(tmp_path / "shared" / "out.txt"))
    team.save_output_to_file(task, "ok")
    assert (tmp_path / "shared" / "out.txt").read_text() == "ok"


def test_workflow_output_file_input_traversal_blocked(root):
    _workflow("reports/{{input}}.md").start("../../x")
    assert not (root.parent / "x.md").exists()

    _workflow("reports/{{input}}.md").start("ok")
    assert (root / "reports" / "ok.md").read_text() == "report"


def test_workflow_async_output_file_input_traversal_blocked(root):
    asyncio.run(_workflow("reports/{{input}}.md").arun("../../x"))
    assert not (root.parent / "x.md").exists()

    asyncio.run(_workflow("reports/{{input}}.md").arun("ok"))
    assert (root / "reports" / "ok.md").read_text() == "report"


@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
def test_task_output_file_traversal_blocked_real_run(root):
    team, _ = _team("../escaped.txt")
    team.start()
    assert not (root.parent / "escaped.txt").exists()
