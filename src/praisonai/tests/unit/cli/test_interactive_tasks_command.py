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
def isolated_runner():
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
    # ``_handle_tasks_command``). The package uses a lazy ``__getattr__`` so the
    # name is *not* a real module attribute until accessed; we therefore install
    # a concrete override on the package ``__dict__`` (which ``__getattr__`` only
    # runs *after*), guaranteeing every ``from ... import get_background_runner``
    # in this process returns exactly the dedicated runner below.
    runner = BackgroundRunner()

    def _dedicated():
        return runner

    # Own the singleton lifecycle explicitly rather than through monkeypatch's
    # save/restore: under a persistent ``--dist loadfile`` worker the value
    # monkeypatch would restore may be a live singleton another file left
    # mutating, so we snapshot and hard-reset it ourselves.
    prev_shared = _bg_runner._shared_runner
    prev_runner_fn = _bg_runner.get_background_runner
    prev_pkg = _bg_pkg.__dict__.get("get_background_runner")
    _bg_runner._shared_runner = runner
    _bg_runner.get_background_runner = _dedicated
    _bg_pkg.get_background_runner = _dedicated
    try:
        yield runner
    finally:
        # Force the shared singleton back to ``None`` so the next resolver
        # rebuilds a clean instance and no dedicated runner from this file leaks
        # into a later module; restore the accessors to their prior state.
        _bg_runner._shared_runner = None if prev_shared is runner else prev_shared
        _bg_runner.get_background_runner = prev_runner_fn
        if prev_pkg is None:
            _bg_pkg.__dict__.pop("get_background_runner", None)
        else:
            _bg_pkg.get_background_runner = prev_pkg


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
