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


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_task_output_file_overwrite_preserves_permissions(root):
    target = root / "shared.txt"
    target.write_text("old")
    os.chmod(target, 0o644)
    team, task = _team("shared.txt")
    team.save_output_to_file(task, "new")
    assert target.read_text() == "new"
    assert target.stat().st_mode & 0o777 == 0o644


@pytest.mark.skipif(os.name == "nt", reason="POSIX hardlinks")
def test_task_output_file_hardlink_does_not_write_outside(root, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    os.link(outside, root / "linked.txt")
    team, task = _team("linked.txt")
    team.save_output_to_file(task, "PWNED")
    assert (root / "linked.txt").read_text() == "PWNED"
    assert outside.read_text() == "secret"


@pytest.mark.skipif(os.name == "nt", reason="POSIX hardlinks")
def test_task_output_file_hardlink_keeps_mode_under_umask(root, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    os.chmod(outside, 0o664)
    os.link(outside, root / "linked.txt")
    team, task = _team("linked.txt")
    old_umask = os.umask(0o077)
    try:
        team.save_output_to_file(task, "new")
    finally:
        os.umask(old_umask)
    assert (root / "linked.txt").stat().st_mode & 0o777 == 0o664
    assert outside.read_text() == "secret"


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="POSIX permission bits")
def test_task_output_file_overwrite_in_readonly_directory(root):
    (root / "ro").mkdir()
    target = root / "ro" / "out.txt"
    target.write_text("old")
    os.chmod(root / "ro", 0o555)
    try:
        team, task = _team("ro/out.txt")
        team.save_output_to_file(task, "new")
    finally:
        os.chmod(root / "ro", 0o755)
    assert target.read_text() == "new"


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
