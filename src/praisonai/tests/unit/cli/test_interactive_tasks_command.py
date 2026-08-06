"""Tests for the interactive REPL /tasks command.

The /tasks command surfaces the shared background runner's tasks from inside
the session, reusing the CLI BackgroundHandler renderer. These tests exercise
the dispatch helper directly with a fake console.
"""

import pytest

il = pytest.importorskip(
    "praisonai.cli.legacy.interactive_legacy",
    reason="interactive_legacy requires optional CLI dependencies",
)

import praisonaiagents.background.runner as _bg_runner
from praisonaiagents.background import get_background_runner, TaskStatus
from praisonaiagents.background.task import BackgroundTask


class _CapturingConsole:
    def __init__(self):
        self.lines = []

    def print(self, *args, **kwargs):
        self.lines.append(" ".join(str(a) for a in args))

    @property
    def text(self):
        return "\n".join(self.lines)


@pytest.fixture(autouse=True)
def _clear_shared_runner():
    # Fully reset the process-wide singleton so these tests are isolated from
    # any background tasks other files scheduled on the shared daemon loop
    # (xdist ``--dist loadfile`` keeps a worker's process alive across files).
    # Rebuilding the runner guarantees ``_handle_tasks_command`` resolves the
    # same empty instance we seed below, rather than a polluted one.
    _bg_runner._shared_runner = None
    runner = get_background_runner()
    runner._tasks.clear()
    yield
    _bg_runner._shared_runner = None


def test_tasks_lists_background_tasks_in_repl(capsys):
    # The BackgroundHandler renders through its own rich Console (stdout),
    # so we assert against captured stdout rather than the dispatch console.
    runner = get_background_runner()
    runner._tasks["t1"] = BackgroundTask(id="t1", name="alpha", status=TaskStatus.RUNNING)
    runner._tasks["t2"] = BackgroundTask(id="t2", name="beta", status=TaskStatus.COMPLETED)

    il._handle_tasks_command(None, _CapturingConsole(), "", {})

    out = capsys.readouterr().out
    assert "t1" in out and "alpha" in out
    assert "t2" in out and "beta" in out


def test_tasks_detail_and_cancel(capsys):
    runner = get_background_runner()
    task = BackgroundTask(id="job1", name="work", status=TaskStatus.RUNNING)
    runner._tasks["job1"] = task

    # Detail renders without error and references the task id.
    il._handle_tasks_command(None, _CapturingConsole(), "job1", {})
    assert "job1" in capsys.readouterr().out

    # Cancel updates the task status.
    il._handle_tasks_command(None, _CapturingConsole(), "cancel job1", {})
    assert runner.get_task("job1").status == TaskStatus.CANCELLED


def test_tasks_empty_list(capsys):
    il._handle_tasks_command(None, _CapturingConsole(), "", {})
    assert "No background tasks" in capsys.readouterr().out
