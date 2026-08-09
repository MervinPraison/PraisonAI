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

import praisonaiagents.background as _bg_pkg
import praisonaiagents.background.runner as _bg_runner
from praisonaiagents.background import TaskStatus
from praisonaiagents.background.runner import BackgroundRunner
from praisonaiagents.background.task import BackgroundTask

# Keep all tests in this module on a single xdist worker. Under
# ``--dist loadfile`` this file is already sent to one worker, but pinning an
# explicit group makes the isolation intent explicit and also holds under
# ``--dist loadgroup``, so a concurrently-running background daemon in another
# worker cannot interleave with the dedicated runner these tests pin.
pytestmark = pytest.mark.xdist_group(name="background_runner_singleton")


class _CapturingConsole:
    def __init__(self):
        self.lines = []

    def print(self, *args, **kwargs):
        self.lines.append(" ".join(str(a) for a in args))

    @property
    def text(self):
        return "\n".join(self.lines)


@pytest.fixture(autouse=True)
def isolated_runner(monkeypatch):
    # Under CI's ``pytest -n 2 --dist loadfile`` a worker process persists
    # across files, so the process-wide ``BackgroundRunner`` singleton — and a
    # live daemon loop another file left running on it — races these tests:
    # a concurrently-mutating task (or a competing fixture rebuilding the
    # singleton) repopulates/empties ``_tasks`` mid-test, surfacing as
    # "No background tasks" and an uncancelled RUNNING task.
    #
    # Merely resetting ``_shared_runner`` (the previous approach) still shared a
    # process-wide object other threads could touch. Instead, pin a *dedicated*
    # runner for the duration of each test and make ``get_background_runner``
    # return exactly it, so no other file's daemon can reach the instance
    # ``_handle_tasks_command`` resolves. Assertions are unchanged — list,
    # detail, and the real CANCELLED status are all still verified.
    #
    # The CLI resolves the runner via ``from praisonaiagents.background import
    # get_background_runner`` (bound on the *package*, imported at call time by
    # ``BackgroundHandler._get_runner``). Patching only the ``runner`` submodule
    # therefore missed the reference the CLI actually reads, so a concurrent
    # cross-file daemon could still swap in the shared runner. Patch the name on
    # the package too so the CLI deterministically sees the dedicated runner.
    runner = BackgroundRunner()
    monkeypatch.setattr(_bg_runner, "_shared_runner", runner, raising=False)
    monkeypatch.setattr(
        _bg_runner, "get_background_runner", lambda: runner, raising=False
    )
    monkeypatch.setattr(
        _bg_pkg, "get_background_runner", lambda: runner, raising=False
    )
    try:
        yield runner
    finally:
        # ``monkeypatch`` restores the patched names, but under a persistent
        # ``--dist loadfile`` worker the process-wide ``_shared_runner`` it
        # restores may be a live singleton another file left mutating. Force it
        # back to ``None`` so the next resolver rebuilds a clean instance and no
        # dedicated runner from this file leaks into a later module.
        _bg_runner._shared_runner = None


def test_tasks_lists_background_tasks_in_repl(capsys, isolated_runner):
    # The BackgroundHandler renders through its own rich Console (stdout),
    # so we assert against captured stdout rather than the dispatch console.
    runner = isolated_runner
    runner._tasks["t1"] = BackgroundTask(id="t1", name="alpha", status=TaskStatus.RUNNING)
    runner._tasks["t2"] = BackgroundTask(id="t2", name="beta", status=TaskStatus.COMPLETED)

    il._handle_tasks_command(None, _CapturingConsole(), "", {}, runner=runner)

    out = capsys.readouterr().out
    assert "t1" in out and "alpha" in out
    assert "t2" in out and "beta" in out


def test_tasks_detail_and_cancel(capsys, isolated_runner):
    runner = isolated_runner
    task = BackgroundTask(id="job1", name="work", status=TaskStatus.RUNNING)
    runner._tasks["job1"] = task

    # Detail renders without error and references the task id.
    il._handle_tasks_command(None, _CapturingConsole(), "job1", {}, runner=runner)
    assert "job1" in capsys.readouterr().out

    # Cancel updates the task status.
    il._handle_tasks_command(None, _CapturingConsole(), "cancel job1", {}, runner=runner)
    assert runner.get_task("job1").status == TaskStatus.CANCELLED


def test_tasks_empty_list(capsys):
    il._handle_tasks_command(None, _CapturingConsole(), "", {})
    assert "No background tasks" in capsys.readouterr().out
