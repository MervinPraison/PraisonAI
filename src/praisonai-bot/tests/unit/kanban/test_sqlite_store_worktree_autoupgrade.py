"""Tests for repo-linked worktree auto-upgrade in SQLiteKanbanStore.create_task.

Refinement 1: a task linked to a git repo auto-upgrades workspace_kind to
'worktree' unless the caller explicitly set a kind or disabled auto_worktree.
"""

import subprocess

import pytest

from praisonai_bot.kanban.sqlite_store import SQLiteKanbanStore


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "f.txt").write_text("x\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    return repo


@pytest.fixture
def store(tmp_path, monkeypatch):
    db = tmp_path / "kanban.db"
    monkeypatch.setenv("PRAISONAI_KANBAN_DB", str(db))
    return SQLiteKanbanStore()


def test_repo_linked_task_auto_upgrades_to_worktree(store, git_repo):
    """A task linked to a git repo (unset kind) becomes 'worktree'."""
    task = store.create_task({"title": "t", "repo_path": str(git_repo)})
    assert task.workspace_kind == "worktree"
    # Branch is derived and persisted up-front for the dispatcher to consume.
    assert task.branch == f"kanban/{task.id}"


def test_repo_linked_via_metadata_auto_upgrades(store, git_repo):
    """repo_path carried in metadata also triggers the auto-upgrade."""
    task = store.create_task(
        {"title": "t", "metadata": {"repo_path": str(git_repo)}}
    )
    assert task.workspace_kind == "worktree"


def test_explicit_default_kind_respected(store, git_repo):
    """An explicit workspace_kind='default' is never auto-upgraded."""
    task = store.create_task(
        {"title": "t", "repo_path": str(git_repo), "workspace_kind": "default"}
    )
    # Explicit default must be respected -> stays default, no branch derived.
    assert task.workspace_kind == "default"
    assert task.branch is None


def test_auto_worktree_false_disables_upgrade(store, git_repo):
    """Board/task-level auto_worktree=false disables the upgrade entirely."""
    task = store.create_task(
        {"title": "t", "repo_path": str(git_repo), "auto_worktree": False}
    )
    assert task.workspace_kind == "default"


def test_non_repo_path_stays_default(store, tmp_path):
    """A path that is not a git repo does not trigger the upgrade."""
    plain = tmp_path / "plain"
    plain.mkdir()
    task = store.create_task({"title": "t", "repo_path": str(plain)})
    assert task.workspace_kind == "default"


def test_no_repo_link_stays_default(store):
    """No repo linkage at all keeps today's shared-cwd default."""
    task = store.create_task({"title": "t"})
    assert task.workspace_kind == "default"
    assert task.branch is None


def test_explicit_worktree_kind_still_derives_branch(store):
    """Explicit workspace_kind='worktree' (no repo) still derives a branch."""
    task = store.create_task({"title": "t", "workspace_kind": "worktree"})
    assert task.workspace_kind == "worktree"
    assert task.branch == f"kanban/{task.id}"


def test_repo_path_preserved_in_metadata(store, git_repo):
    """The repo linkage that drove the upgrade is retained in metadata."""
    task = store.create_task({"title": "t", "repo_path": str(git_repo)})
    # Linkage must not be discarded: it is persisted so a consumer can locate
    # the isolating repository between create and dispatch.
    assert task.metadata.get("repo_path") == str(git_repo)
    # Re-read from the store to confirm it round-trips through persistence.
    reloaded = store.get_task(task.id)
    assert reloaded.metadata.get("repo_path") == str(git_repo)


def test_explicit_metadata_repo_path_not_overwritten(store, git_repo):
    """An explicit metadata.repo_path wins over the top-level repo_path."""
    task = store.create_task({
        "title": "t",
        "repo_path": str(git_repo),
        "metadata": {"repo_path": "/explicit/path"},
    })
    assert task.metadata.get("repo_path") == "/explicit/path"
