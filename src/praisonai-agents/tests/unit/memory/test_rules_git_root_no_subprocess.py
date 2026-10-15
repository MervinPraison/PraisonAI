"""Regression tests for #5819: no `git` subprocess per agent outside a repo."""
import subprocess
from pathlib import Path

import pytest

from praisonaiagents.memory.rules_manager import RulesManager


@pytest.fixture
def no_git_env(monkeypatch):
    monkeypatch.delenv("GIT_DIR", raising=False)
    monkeypatch.delenv("GIT_WORK_TREE", raising=False)


@pytest.fixture
def run_calls(monkeypatch):
    calls = []
    orig = subprocess.run

    def spy(*args, **kwargs):
        calls.append(args[0] if args else kwargs.get("args"))
        return orig(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    return calls


def _git_calls(calls):
    return [c for c in calls if "git" in str(c)]


def test_non_git_dir_spawns_no_git_subprocess(tmp_path, no_git_env, run_calls):
    for _ in range(3):
        manager = RulesManager(workspace_path=str(tmp_path))
        assert manager._find_git_root() is None
    assert _git_calls(run_calls) == []


def test_agents_in_non_git_dir_spawn_no_git_subprocess(tmp_path, monkeypatch, no_git_env, run_calls):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from praisonaiagents import Agent

    # _init_rules_manager swallows errors, so prove construction completed.
    built = []
    orig_init = RulesManager.__init__

    def counting_init(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        built.append(self)

    monkeypatch.setattr(RulesManager, "__init__", counting_init)

    for i in range(3):
        agent = Agent(name=f"a{i}", instructions="x", output="silent")
        agent._init_rules_manager()
    assert len(built) == 3
    assert _git_calls(run_calls) == []


@pytest.mark.parametrize("var", ["GIT_DIR", "GIT_WORK_TREE"])
def test_git_env_var_still_uses_rev_parse(tmp_path, monkeypatch, no_git_env, var):
    # No ancestor .git, but GIT_DIR/GIT_WORK_TREE lets git locate the repo.
    monkeypatch.setenv(var, "/elsewhere")
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="/repo/root\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    manager = RulesManager(workspace_path=str(tmp_path))
    calls.clear()
    assert manager._find_git_root() == Path("/repo/root")
    assert calls == [["git", "rev-parse", "--show-toplevel"]]


def test_git_repo_root_found(tmp_path, no_git_env, run_calls):
    (tmp_path / ".git").mkdir()
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    manager = RulesManager(workspace_path=str(sub))
    assert manager._find_git_root() == tmp_path.resolve()
    assert _git_calls(run_calls) == []


def test_worktree_git_file_root_found(tmp_path, no_git_env, run_calls):
    # In worktrees/submodules `.git` is a file, not a directory.
    (tmp_path / ".git").write_text("gitdir: /elsewhere/.git/worktrees/wt\n")
    sub = tmp_path / "pkg"
    sub.mkdir()
    manager = RulesManager(workspace_path=str(sub))
    assert manager._find_git_root() == tmp_path.resolve()
    assert _git_calls(run_calls) == []
