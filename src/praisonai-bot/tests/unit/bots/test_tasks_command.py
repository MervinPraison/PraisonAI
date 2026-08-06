"""Tests for the /tasks background-task chat command.

Exercises the shared ``handle_tasks_command`` handler directly (no platform
SDK required) and its registration on the command registry. Covers listing,
detail, cancel, and per-user scoping.
"""

from praisonaiagents.background import BackgroundRunner, TaskStatus
from praisonaiagents.background.task import BackgroundTask

from praisonai_bot.bots._commands import (
    CommandRegistry,
    handle_tasks_command,
)


def _make_runner(*tasks: BackgroundTask) -> BackgroundRunner:
    runner = BackgroundRunner()
    for task in tasks:
        runner._tasks[task.id] = task
    return runner


def test_tasks_command_registered():
    registry = CommandRegistry()
    assert "tasks" in registry.get_command_names()
    assert registry.get_command("tasks")["builtin"] is True


def test_tasks_lists_background_tasks():
    t1 = BackgroundTask(id="aaa", name="research", status=TaskStatus.RUNNING)
    t2 = BackgroundTask(id="bbb", name="summary", status=TaskStatus.COMPLETED)
    runner = _make_runner(t1, t2)

    out = handle_tasks_command("u1", None, runner=runner)
    assert "aaa" in out and "research" in out
    assert "bbb" in out and "summary" in out
    assert "running" in out
    assert "completed" in out


def test_tasks_empty():
    out = handle_tasks_command("u1", None, runner=_make_runner())
    assert "No background tasks" in out


def test_tasks_detail_shows_result():
    task = BackgroundTask(id="ccc", name="job", status=TaskStatus.COMPLETED)
    task.result = "done-value"
    out = handle_tasks_command("u1", "ccc", runner=_make_runner(task))
    assert "ccc" in out
    assert "done-value" in out


def test_tasks_detail_not_found():
    out = handle_tasks_command("u1", "missing", runner=_make_runner())
    assert "not found" in out.lower()


def test_tasks_cancel_running_task():
    task = BackgroundTask(id="ddd", name="job", status=TaskStatus.RUNNING)
    runner = _make_runner(task)
    out = handle_tasks_command("u1", "cancel ddd", runner=runner)
    assert "Cancelled" in out
    assert runner.get_task("ddd").status == TaskStatus.CANCELLED


def test_tasks_cancel_requires_id():
    out = handle_tasks_command("u1", "cancel", runner=_make_runner())
    assert "Usage" in out


def test_bot_tasks_command_scoped_to_user():
    # Tasks carry an owner in metadata; a user must see only their own.
    mine = BackgroundTask(
        id="mine", name="my-task", status=TaskStatus.RUNNING,
        metadata={"user_id": "u1"},
    )
    theirs = BackgroundTask(
        id="theirs", name="their-task", status=TaskStatus.RUNNING,
        metadata={"user_id": "u2"},
    )
    runner = _make_runner(mine, theirs)

    out = handle_tasks_command("u1", None, runner=runner)
    assert "mine" in out
    assert "theirs" not in out

    # And u1 cannot inspect or cancel u2's task by id.
    detail = handle_tasks_command("u1", "theirs", runner=runner)
    assert "not found" in detail.lower()
    cancel = handle_tasks_command("u1", "cancel theirs", runner=runner)
    assert "not found" in cancel.lower()
    assert runner.get_task("theirs").status == TaskStatus.RUNNING
