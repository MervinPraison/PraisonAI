"""Tests for git-aware, path-independent project identity (Issue #2917).

The CLI scopes session history by a project id. Previously that id was a hash
of the absolute git-root path, so moving/cloning a repo or using ``git
worktree`` orphaned session history. ``resolve_project_identity`` now derives a
repository-following identity (git remote → root commit → cached id → path).
"""

import os
import subprocess
from pathlib import Path

import pytest

from praisonai_code.cli.utils import project as project_mod
from praisonai_code.cli.utils.project import (
    get_legacy_project_id,
    get_project_id,
    normalize_git_remote,
    resolve_project_identity,
)


def _git(cwd, *args):
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@e.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@e.com",
        },
    )


def _has_git() -> bool:
    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True)
        return True
    except Exception:
        return False


requires_git = pytest.mark.skipif(not _has_git(), reason="git not available")


def test_normalize_git_remote_equivalent_forms_collapse():
    https = normalize_git_remote("https://github.com/owner/repo.git")
    ssh = normalize_git_remote("git@github.com:owner/repo.git")
    no_git = normalize_git_remote("https://github.com/owner/repo")
    creds = normalize_git_remote("https://user:token@github.com/owner/repo.git")
    assert https == "github.com/owner/repo"
    assert https == ssh == no_git == creds


def test_normalize_git_remote_case_insensitive_host():
    assert normalize_git_remote("https://GitHub.com/Owner/Repo.git") == "github.com/Owner/Repo"


def test_normalize_git_remote_invalid_returns_none():
    assert normalize_git_remote("") is None
    assert normalize_git_remote("not-a-url") is None


def test_normalize_git_remote_hostless_file_url():
    # Host-less remotes must still yield a stable identity from their path
    # instead of falling through to root-commit/cached-id/path (Greptile P2).
    assert normalize_git_remote("file:///srv/repos/project.git") == "srv/repos/project"
    assert normalize_git_remote("file:///srv/repos/project.git") == normalize_git_remote(
        "file:///srv/repos/project"
    )


def test_non_git_dir_uses_path_source(tmp_path):
    pid, source = resolve_project_identity(str(tmp_path))
    assert source == "path"
    assert pid == get_legacy_project_id(str(tmp_path))
    assert len(pid) == 8


@requires_git
def test_same_remote_two_paths_share_identity(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    for d in (a, b):
        d.mkdir()
        _git(d, "init")
        _git(d, "remote", "add", "origin", "https://github.com/owner/repo.git")

    id_a, src_a = resolve_project_identity(str(a))
    id_b, src_b = resolve_project_identity(str(b))
    assert src_a == src_b == "git-remote"
    assert id_a == id_b


@requires_git
def test_relocated_repo_keeps_identity(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _git(src, "init")
    _git(src, "remote", "add", "origin", "git@github.com:owner/repo.git")
    before, _ = resolve_project_identity(str(src))

    moved = tmp_path / "moved"
    src.rename(moved)
    after, _ = resolve_project_identity(str(moved))
    assert before == after


@requires_git
def test_root_commit_identity_when_no_remote(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / "f.txt").write_text("x")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")

    pid, source = resolve_project_identity(str(repo))
    assert source == "root-commit"
    assert len(pid) == 8


@requires_git
def test_worktrees_share_identity(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / "f.txt").write_text("x")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")

    wt = tmp_path / "wt"
    _git(repo, "worktree", "add", str(wt))

    id_repo, _ = resolve_project_identity(str(repo))
    id_wt, _ = resolve_project_identity(str(wt))
    assert id_repo == id_wt


@requires_git
def test_cached_id_when_no_remote_or_commit(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")

    pid, source = resolve_project_identity(str(repo))
    assert source == "cached-id"
    assert (repo / ".git" / "praisonai-project").exists()
    # Stable across calls.
    pid2, _ = resolve_project_identity(str(repo))
    assert pid == pid2


@requires_git
def test_root_commit_stable_across_orphan_branches(tmp_path):
    # Switching between unmerged orphan branches must not change identity
    # (Greptile P2): root commit is enumerated across all refs, deterministically.
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / "f.txt").write_text("x")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")
    id_main, src_main = resolve_project_identity(str(repo))
    assert src_main == "root-commit"

    _git(repo, "checkout", "--orphan", "other")
    (repo / "g.txt").write_text("y")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "orphan")
    id_other, src_other = resolve_project_identity(str(repo))
    assert src_other == "root-commit"
    assert id_main == id_other


@requires_git
def test_cached_id_loser_reads_persisted_winner(tmp_path, monkeypatch):
    # Simulate a concurrent first-run losing the exclusive create: it must
    # return the persisted winner, not its own unpersisted id (Greptile P1).
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")

    winner, _ = resolve_project_identity(str(repo))
    cached_file = repo / ".git" / "praisonai-project"
    persisted = cached_file.read_text().strip()

    from praisonai_code.cli.utils.project import get_or_create_cached_id

    # Now a fresh call must reuse the persisted id, never mint a new one.
    again = get_or_create_cached_id(str(repo))
    assert again == persisted
    later, _ = resolve_project_identity(str(repo))
    assert later == winner


def test_get_project_id_returns_only_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(
        project_mod, "resolve_project_identity", lambda path=None: ("abcd1234", "path")
    )
    assert get_project_id(str(tmp_path)) == "abcd1234"
