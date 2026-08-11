"""Tests for per-run git-worktree isolation on `praisonai run` (issue #3253).

`run.py`'s `_worktree_isolation` context manager wires the core
`GitWorktreeAdapter` into the CLI run lifecycle: when `--worktree` is set and the
cwd is a git repo it provisions a fresh worktree/branch, chdirs into it for the
run, then tears it down (or keeps it with `--keep`). It degrades to a transparent
no-op outside a git repo so callers can wrap unconditionally.
"""

import os
import subprocess

import pytest

from praisonai_code.cli.commands import run as run_cmd


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "seed.txt").write_text("seed\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    return repo


def test_disabled_is_noop(tmp_path):
    """enabled=False never changes cwd and yields None."""
    start = os.getcwd()
    try:
        os.chdir(tmp_path)
        with run_cmd._worktree_isolation(False, "task") as path:
            assert path is None
            assert os.getcwd() == str(tmp_path)
    finally:
        os.chdir(start)


def test_non_git_dir_degrades(tmp_path):
    """Outside a git repo, isolation degrades to a no-op in the same directory."""
    start = os.getcwd()
    try:
        os.chdir(tmp_path)
        with run_cmd._worktree_isolation(True, "task") as path:
            assert path is None
            assert os.getcwd() == str(tmp_path)
    finally:
        os.chdir(start)


def test_provisions_worktree_and_tears_down(git_repo):
    """Inside a git repo, the run happens in a worktree that is removed on exit."""
    start = os.getcwd()
    try:
        os.chdir(git_repo)
        with run_cmd._worktree_isolation(True, "my task") as path:
            assert path is not None
            assert os.path.realpath(os.getcwd()) == os.path.realpath(path)
            # Running inside an isolated worktree, not the original repo root.
            assert os.path.realpath(path) != os.path.realpath(str(git_repo))
            assert os.path.exists(os.path.join(path, "seed.txt"))
        # cwd restored and worktree removed by default.
        assert os.getcwd() == str(git_repo)
        assert not os.path.exists(path)
    finally:
        os.chdir(start)


def test_keep_retains_worktree(git_repo):
    """--keep retains the worktree/branch after the run for review."""
    start = os.getcwd()
    kept_path = None
    try:
        os.chdir(git_repo)
        with run_cmd._worktree_isolation(True, "keep me", keep=True) as path:
            kept_path = path
            assert path is not None
        assert os.getcwd() == str(git_repo)
        assert os.path.exists(kept_path)
    finally:
        if kept_path and os.path.exists(kept_path):
            _git(git_repo, "worktree", "remove", "--force", kept_path)
        os.chdir(start)


def test_cwd_restored_on_error(git_repo):
    """cwd is restored and the worktree torn down even when the run raises."""
    start = os.getcwd()
    try:
        os.chdir(git_repo)
        captured = None
        with pytest.raises(RuntimeError):
            with run_cmd._worktree_isolation(True, "boom") as path:
                captured = path
                raise RuntimeError("run failed")
        assert os.getcwd() == str(git_repo)
        assert captured is not None
        assert not os.path.exists(captured)
    finally:
        os.chdir(start)


def test_untracked_output_is_preserved_on_a_branch(git_repo):
    """A run that only creates new (untracked) files must not lose them.

    ``git diff`` doesn't see untracked files, so the old cleanup force-removed
    the worktree and silently deleted brand-new output. The changes must now be
    committed to the isolated branch and that branch retained for review.
    """
    start = os.getcwd()
    try:
        os.chdir(git_repo)
        with run_cmd._worktree_isolation(True, "make output") as path:
            # Agent output is a brand-new, untracked file.
            (open(os.path.join(path, "generated.txt"), "w")).write("result\n")
        # Worktree checkout is pruned, but the branch (with the output) survives.
        assert not os.path.exists(path)
        branches = _git(git_repo, "branch", "--list", "praisonai/*").stdout
        assert "praisonai/" in branches
        # The committed output is retrievable from the retained branch.
        kept_branch = branches.strip().split()[-1]
        show = _git(git_repo, "show", f"{kept_branch}:generated.txt")
        assert show.returncode == 0
        assert "result" in show.stdout
    finally:
        # Clean up any retained praisonai/* branches created by this test.
        for line in _git(git_repo, "branch", "--list", "praisonai/*").stdout.split("\n"):
            b = line.strip().lstrip("* ").strip()
            if b:
                _git(git_repo, "branch", "-D", b)
        os.chdir(start)


def test_identical_targets_get_independent_worktrees(git_repo):
    """Two runs of the same target must not resolve to the same worktree."""
    start = os.getcwd()
    try:
        os.chdir(git_repo)
        with run_cmd._worktree_isolation(True, "same", keep=True) as path_a:
            with run_cmd._worktree_isolation(True, "same", keep=True) as path_b:
                assert path_a is not None and path_b is not None
                assert os.path.realpath(path_a) != os.path.realpath(path_b)
    finally:
        for line in _git(git_repo, "worktree", "list", "--porcelain").stdout.split("\n"):
            if line.startswith("worktree ") and "worktrees" in line:
                _git(git_repo, "worktree", "remove", "--force", line.split(" ", 1)[1])
        os.chdir(start)
