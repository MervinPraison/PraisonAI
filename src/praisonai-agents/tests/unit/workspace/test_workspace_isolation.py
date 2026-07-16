"""Tests for workspace isolation protocol and adapters."""

import subprocess
from pathlib import Path

import pytest

from praisonaiagents.workspace import (
    WorkspaceIsolationProtocol,
    NoIsolationAdapter,
    GitWorktreeAdapter,
)


def _git_available() -> bool:
    try:
        return subprocess.run(
            ["git", "--version"], capture_output=True
        ).returncode == 0
    except (FileNotFoundError, OSError):
        return False


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.co"], cwd=path, capture_output=True, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "t"], cwd=path, capture_output=True, check=True
    )
    (path / "file.txt").write_text("base\n")
    subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=path, capture_output=True, check=True
    )


def test_adapters_satisfy_protocol():
    assert isinstance(NoIsolationAdapter(), WorkspaceIsolationProtocol)
    assert isinstance(GitWorktreeAdapter(), WorkspaceIsolationProtocol)


def test_no_isolation_shares_root(tmp_path):
    adapter = NoIsolationAdapter(root=tmp_path)
    root = str(tmp_path.resolve())
    assert adapter.create("a") == root
    assert adapter.create("b") == root
    assert adapter.path("a") == root
    # reset/remove are no-ops
    adapter.reset("a")
    adapter.remove("a")


def test_git_worktree_degrades_when_not_a_repo(tmp_path):
    adapter = GitWorktreeAdapter(root=tmp_path)
    assert adapter.available is False
    assert adapter.create("run") == str(tmp_path.resolve())
    # No-ops, no exceptions.
    adapter.reset("run")
    adapter.remove("run")


@pytest.mark.skipif(not _git_available(), reason="git not available")
def test_concurrent_runs_get_independent_worktrees(tmp_path):
    _init_repo(tmp_path)
    adapter = GitWorktreeAdapter(root=tmp_path)
    assert adapter.available is True

    path_a = Path(adapter.create("agent-a"))
    path_b = Path(adapter.create("agent-b"))

    assert path_a != path_b
    assert path_a.exists() and path_b.exists()

    # Independent edits to the same file must not clobber each other.
    (path_a / "file.txt").write_text("edit-a\n")
    (path_b / "file.txt").write_text("edit-b\n")

    assert (path_a / "file.txt").read_text() == "edit-a\n"
    assert (path_b / "file.txt").read_text() == "edit-b\n"

    adapter.remove("agent-a")
    adapter.remove("agent-b")
    assert not path_a.exists()
    assert not path_b.exists()


@pytest.mark.skipif(not _git_available(), reason="git not available")
def test_reset_restores_clean_state(tmp_path):
    _init_repo(tmp_path)
    adapter = GitWorktreeAdapter(root=tmp_path)
    wt = Path(adapter.create("run"))

    (wt / "file.txt").write_text("dirty\n")
    (wt / "untracked.txt").write_text("new\n")

    adapter.reset("run")

    assert (wt / "file.txt").read_text() == "base\n"
    assert not (wt / "untracked.txt").exists()

    adapter.remove("run")
