"""Unit tests for kanban dispatcher per-task git worktree isolation."""

import os
import subprocess

import pytest

from praisonai_bot.gateway.kanban_dispatcher import KanbanDispatcher


class _FakeTask:
    def __init__(self, task_id, workspace_kind="default", board="default"):
        self.id = task_id
        self.board = board
        self.title = task_id
        self.body = ""
        self.workspace_kind = workspace_kind

    def to_dict(self):
        return {"id": self.id, "workspace_kind": self.workspace_kind}


class _FakeStore:
    def __init__(self):
        self.updates = {}
        self.moves = []
        self.comments = []

    def update_task(self, task_id, updates):
        self.updates.setdefault(task_id, {}).update(updates)

    def move_task(self, task_id, status):
        self.moves.append((task_id, status))

    def add_comment(self, task_id, author, text):
        self.comments.append((task_id, author, text))


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path):
    """A minimal git repo with one committed file on a base branch."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "shared.txt").write_text("line1\nline2\nline3\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    return repo


def _dispatcher_in(repo):
    """A dispatcher whose git commands run inside ``repo``."""
    d = KanbanDispatcher()
    original = d._run_git

    def _run_git(*args, cwd=None):
        return original(*args, cwd=cwd or str(repo))

    d._run_git = _run_git
    # Keep worktrees inside the tmp repo dir.
    d._worktree_root = lambda: str(repo / ".wt")
    return d


def _spy_popen(dispatcher, calls):
    """Wrap the real Popen so cwd is recorded but the process still runs.

    Uses a harmless ``true`` command so no real agent is launched.
    """
    dispatcher._build_execution_command = lambda task: ["true"]
    from praisonai_bot.gateway import kanban_dispatcher as kd
    real_popen = kd.subprocess.Popen

    def _wrapped(cmd, **kwargs):
        # Only record the worker spawn (the ["true"] command), not the git
        # subprocess.run calls that also route through Popen.
        if cmd == ["true"]:
            calls.append(kwargs.get("cwd"))
        return real_popen(cmd, **kwargs)

    return _wrapped


@pytest.mark.asyncio
async def test_worker_spawned_in_own_worktree(git_repo, monkeypatch):
    """workspace_kind='worktree' tasks get distinct cwd worktrees."""
    d = _dispatcher_in(git_repo)
    store = _FakeStore()

    calls = []
    from praisonai_bot.gateway import kanban_dispatcher as kd
    monkeypatch.setattr(kd.subprocess, "Popen", _spy_popen(d, calls), raising=True)

    ok_a = await d._spawn_worker(_FakeTask("t_a", "worktree"), store)
    ok_b = await d._spawn_worker(_FakeTask("t_b", "worktree"), store)

    assert ok_a and ok_b
    cwds = [c for c in calls if c]
    assert len(cwds) == 2
    assert cwds[0] != cwds[1]
    assert store.updates["t_a"]["branch"] == "kanban/t_a"
    assert store.updates["t_b"]["branch"] == "kanban/t_b"


@pytest.mark.asyncio
async def test_default_kind_shares_cwd(git_repo, monkeypatch):
    """workspace_kind='default' => no worktree, cwd stays None (shared)."""
    d = _dispatcher_in(git_repo)
    store = _FakeStore()

    calls = []
    from praisonai_bot.gateway import kanban_dispatcher as kd
    monkeypatch.setattr(kd.subprocess, "Popen", _spy_popen(d, calls), raising=True)

    ok = await d._spawn_worker(_FakeTask("t_default", "default"), store)
    assert ok
    assert calls == [None]
    assert "t_default" not in store.updates


def test_worktree_path_persisted(git_repo):
    """_prepare_worktree persists branch + worktree_path on the task row."""
    d = _dispatcher_in(git_repo)
    store = _FakeStore()

    path = d._prepare_worktree(_FakeTask("t_p", "worktree"), store)
    assert path is not None
    assert os.path.isdir(path)
    assert store.updates["t_p"]["branch"] == "kanban/t_p"
    assert store.updates["t_p"]["worktree_path"] == path


def test_clean_integration_removes_worktree(git_repo):
    """A non-conflicting branch merges and the worktree is removed."""
    d = _dispatcher_in(git_repo)
    store = _FakeStore()

    path = d._prepare_worktree(_FakeTask("t_ok", "worktree"), store)
    d._worktrees = {"t_ok": (path, "kanban/t_ok")}
    # Edit a *different* file so the merge is clean.
    (git_repo / ".wt" / "t_ok" / "new.txt").write_text("hello\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-m", "add new")

    conflicted = d._integrate_worktree("t_ok", store)

    assert conflicted is False
    assert not os.path.exists(path)
    assert "t_ok" not in d._worktrees
    # File landed on base branch.
    assert (git_repo / "new.txt").exists()


def test_conflict_routes_to_blocked(git_repo):
    """Overlapping edits on the same line conflict => task blocked."""
    d = _dispatcher_in(git_repo)
    store = _FakeStore()

    # Branch the worktree from the original base commit first.
    path = d._prepare_worktree(_FakeTask("t_x", "worktree"), store)
    d._worktrees = {"t_x": (path, "kanban/t_x")}
    # Worktree edits the first line.
    (git_repo / ".wt" / "t_x" / "shared.txt").write_text("WORKTREE-EDIT\nline2\nline3\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-m", "worktree edits shared")

    # Base independently edits the same first line -> divergent, conflicting.
    (git_repo / "shared.txt").write_text("BASE-EDIT\nline2\nline3\n")
    _git(git_repo, "add", "-A")
    _git(git_repo, "commit", "-m", "base edits shared")

    conflicted = d._integrate_worktree("t_x", store)

    assert conflicted is True
    assert ("t_x", "blocked") in store.moves
    assert any("merge conflict" in c[2] for c in store.comments)
    # Base branch not silently overwritten: original base edit intact.
    assert (git_repo / "shared.txt").read_text().startswith("BASE-EDIT")
