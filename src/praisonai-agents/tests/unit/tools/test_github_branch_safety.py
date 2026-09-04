import subprocess

import pytest

from praisonaiagents.tools import github_tools


def _fake_git_factory(responses, calls):
    """Build a fake subprocess.run that records calls and serves canned output."""

    def fake_run(cmd, check=False, capture_output=False, text=False):
        calls.append(cmd)
        assert cmd[0] == "git"
        key = tuple(cmd[1:])
        # Match on a prefix of the git args
        for prefix, result in responses.items():
            if key[: len(prefix)] == prefix:
                stdout, rc = result
                if rc != 0 and check:
                    raise subprocess.CalledProcessError(rc, cmd, stderr="boom")
                return subprocess.CompletedProcess(cmd, rc, stdout=stdout, stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    return fake_run


def _run_tool(func, *args, **kwargs):
    # FunctionTool.__call__ forwards positional/keyword args to the wrapped fn.
    return func(*args, **kwargs)


def _call(monkeypatch, responses):
    calls = []
    monkeypatch.setattr(subprocess, "run", _fake_git_factory(responses, calls))
    return calls


def test_default_branch_auto_creates_agent_branch(monkeypatch):
    responses = {
        ("status", "--porcelain"): ("M file\n", 0),
        ("rev-parse", "--abbrev-ref", "HEAD"): ("main\n", 0),
        ("symbolic-ref", "refs/remotes/origin/HEAD"): ("refs/remotes/origin/main\n", 0),
    }
    calls = _call(monkeypatch, responses)
    result = _run_tool(github_tools.github_commit_and_push, "fix parser")
    assert "praisonai/" in result
    assert "default branch 'main'" in result
    # push must target the new agent branch, never main, never --force
    push_cmds = [c for c in calls if c[:2] == ["git", "push"]]
    assert push_cmds, "expected a push"
    for c in push_cmds:
        assert "--force" not in c
        assert "main" not in c
        assert any(a.startswith("praisonai/") for a in c)


def test_explicit_main_refused(monkeypatch):
    responses = {
        ("status", "--porcelain"): ("M file\n", 0),
        ("rev-parse", "--abbrev-ref", "HEAD"): ("praisonai/work\n", 0),
        ("symbolic-ref", "refs/remotes/origin/HEAD"): ("refs/remotes/origin/main\n", 0),
    }
    calls = _call(monkeypatch, responses)
    result = _run_tool(github_tools.github_commit_and_push, "fix", branch="main")
    # target==default triggers auto-branch (rule 2) rather than a hard refusal
    assert "praisonai/" in result
    push_cmds = [c for c in calls if c[:2] == ["git", "push"]]
    for c in push_cmds:
        assert "main" not in c


def test_release_branch_refused(monkeypatch):
    responses = {
        ("status", "--porcelain"): ("M file\n", 0),
        ("rev-parse", "--abbrev-ref", "HEAD"): ("praisonai/work\n", 0),
        ("symbolic-ref", "refs/remotes/origin/HEAD"): ("refs/remotes/origin/main\n", 0),
        ("config", "user.email"): ("me@example.com\n", 0),
        ("merge-base", "origin/main", "HEAD"): ("abc123\n", 0),
        ("log", "--format=%ae", "abc123..HEAD"): ("other@x.com\nme@example.com\n", 0),
    }
    calls = _call(monkeypatch, responses)
    result = _run_tool(github_tools.github_commit_and_push, "fix", branch="release/v2")
    assert "Error" in result
    assert "authored by someone else" in result
    assert not [c for c in calls if c[:2] == ["git", "push"]]


def test_override_allows_unsafe(monkeypatch):
    responses = {
        ("status", "--porcelain"): ("M file\n", 0),
        ("rev-parse", "--abbrev-ref", "HEAD"): ("release/v2\n", 0),
        ("symbolic-ref", "refs/remotes/origin/HEAD"): ("refs/remotes/origin/main\n", 0),
        ("show-ref", "--verify", "--quiet", "refs/remotes/origin/release/v2"): ("", 1),
    }
    calls = _call(monkeypatch, responses)
    result = _run_tool(
        github_tools.github_commit_and_push,
        "fix",
        branch="release/v2",
        allow_unsafe_branch=True,
    )
    assert "Successfully" in result
    push_cmds = [c for c in calls if c[:2] == ["git", "push"]]
    assert push_cmds
    for c in push_cmds:
        assert "--force" not in c


def test_diverged_remote_refused_no_force(monkeypatch):
    responses = {
        ("status", "--porcelain"): ("M file\n", 0),
        ("rev-parse", "--abbrev-ref", "HEAD"): ("feature/x\n", 0),
        ("symbolic-ref", "refs/remotes/origin/HEAD"): ("refs/remotes/origin/main\n", 0),
        ("config", "user.email"): ("me@example.com\n", 0),
        ("merge-base", "origin/main", "HEAD"): ("abc\n", 0),
        ("log", "--format=%ae", "abc..HEAD"): ("me@example.com\n", 0),
        ("show-ref", "--verify", "--quiet", "refs/remotes/origin/feature/x"): ("", 0),
        ("merge-base", "--is-ancestor", "origin/feature/x", "HEAD"): ("", 1),
    }
    calls = _call(monkeypatch, responses)
    result = _run_tool(github_tools.github_commit_and_push, "fix", branch="feature/x")
    assert "Error" in result
    assert "diverged" in result
    # no push, and certainly no --force anywhere
    for c in calls:
        assert "--force" not in c
    assert not [c for c in calls if c[:2] == ["git", "push"]]


def test_agent_branch_flow_unchanged(monkeypatch):
    responses = {
        ("status", "--porcelain"): ("M file\n", 0),
        ("rev-parse", "--abbrev-ref", "HEAD"): ("praisonai/mywork\n", 0),
        ("symbolic-ref", "refs/remotes/origin/HEAD"): ("refs/remotes/origin/main\n", 0),
    }
    calls = _call(monkeypatch, responses)
    result = _run_tool(github_tools.github_commit_and_push, "fix")
    assert "Successfully committed and pushed" in result
    assert "praisonai/mywork" in result
    push_cmds = [c for c in calls if c[:2] == ["git", "push"]]
    assert push_cmds
    for c in push_cmds:
        assert "praisonai/mywork" in c
        assert "--force" not in c


def test_no_changes_returns_early(monkeypatch):
    responses = {("status", "--porcelain"): ("", 0)}
    calls = _call(monkeypatch, responses)
    result = _run_tool(github_tools.github_commit_and_push, "noop")
    assert result == "No changes to commit."
    assert not [c for c in calls if c[:2] == ["git", "push"]]


def test_existing_local_target_not_reset(monkeypatch):
    # Agent is on one branch but targets an existing local branch; the tool
    # must switch with a plain checkout (never ``-B``) so the target's
    # local-only commits are preserved.
    responses = {
        ("status", "--porcelain"): ("M file\n", 0),
        ("rev-parse", "--abbrev-ref", "HEAD"): ("praisonai/current\n", 0),
        ("symbolic-ref", "refs/remotes/origin/HEAD"): ("refs/remotes/origin/main\n", 0),
        ("show-ref", "--verify", "--quiet", "refs/heads/praisonai/other"): ("", 0),
    }
    calls = _call(monkeypatch, responses)
    result = _run_tool(
        github_tools.github_commit_and_push, "fix", branch="praisonai/other"
    )
    assert "Successfully" in result
    checkouts = [c for c in calls if c[:2] == ["git", "checkout"]]
    assert checkouts, "expected a checkout to the target branch"
    for c in checkouts:
        assert "-B" not in c, "existing branch must not be force-reset with -B"


def test_diverged_agent_branch_refused_no_force(monkeypatch):
    # Divergence (force-push) is never overridable and applies even to
    # agent-prefixed branches.
    responses = {
        ("status", "--porcelain"): ("M file\n", 0),
        ("rev-parse", "--abbrev-ref", "HEAD"): ("praisonai/work\n", 0),
        ("symbolic-ref", "refs/remotes/origin/HEAD"): ("refs/remotes/origin/main\n", 0),
        ("show-ref", "--verify", "--quiet", "refs/remotes/origin/praisonai/work"): ("", 0),
        ("merge-base", "--is-ancestor", "origin/praisonai/work", "HEAD"): ("", 1),
    }
    calls = _call(monkeypatch, responses)
    result = _run_tool(github_tools.github_commit_and_push, "fix")
    assert "Error" in result
    assert "diverged" in result
    for c in calls:
        assert "--force" not in c
    assert not [c for c in calls if c[:2] == ["git", "push"]]


def test_refusal_leaves_changes_uncommitted(monkeypatch):
    # A refused push must not commit first — the working changes must survive
    # so a retry can succeed.
    responses = {
        ("status", "--porcelain"): ("M file\n", 0),
        ("rev-parse", "--abbrev-ref", "HEAD"): ("release/v2\n", 0),
        ("symbolic-ref", "refs/remotes/origin/HEAD"): ("refs/remotes/origin/main\n", 0),
        ("config", "user.email"): ("me@example.com\n", 0),
        ("merge-base", "origin/main", "HEAD"): ("abc\n", 0),
        ("log", "--format=%ae", "abc..HEAD"): ("other@x.com\n", 0),
    }
    calls = _call(monkeypatch, responses)
    result = _run_tool(github_tools.github_commit_and_push, "fix", branch="release/v2")
    assert "Error" in result
    assert not [c for c in calls if c[:2] == ["git", "commit"]]
    assert not [c for c in calls if c[:2] == ["git", "push"]]


def test_slugify_and_auto_branch():
    assert github_tools._slugify("Fix: parser!! bug") == "fix-parser-bug"
    name = github_tools._auto_branch_name("Fix parser")
    assert name.startswith("praisonai/fix-parser-")
    assert github_tools._branch_push_safety("praisonai/anything") is None


def test_create_branch_validates_full_ref(monkeypatch):
    # Validation must check the literal ``refs/heads/<name>`` ref so Git cannot
    # expand checkout shorthand (e.g. ``@{-1}``) before ``checkout -B`` runs.
    responses = {
        ("rev-parse", "--is-inside-work-tree"): ("true\n", 0),
    }
    calls = _call(monkeypatch, responses)
    _run_tool(github_tools.github_create_branch, "praisonai/fix")
    ref_checks = [c for c in calls if c[:2] == ["git", "check-ref-format"]]
    assert ref_checks, "expected a check-ref-format validation"
    for c in ref_checks:
        assert "--branch" not in c, "must not use --branch (expands shorthand)"
        assert "refs/heads/praisonai/fix" in c


def test_create_branch_rejects_checkout_shorthand(monkeypatch):
    # ``@{-1}`` is a valid checkout shorthand but an invalid full ref, so it must
    # be rejected before any checkout runs (no destructive branch reset).
    responses = {
        ("rev-parse", "--is-inside-work-tree"): ("true\n", 0),
        ("check-ref-format", "refs/heads/@{-1}"): ("", 1),
    }
    calls = _call(monkeypatch, responses)
    result = _run_tool(github_tools.github_create_branch, "@{-1}")
    assert "invalid branch name" in result
    assert not [c for c in calls if c[:2] == ["git", "checkout"]]


def test_create_branch_accepts_slash_names(monkeypatch):
    # Ordinary slash-containing branch names must still be created.
    responses = {
        ("rev-parse", "--is-inside-work-tree"): ("true\n", 0),
    }
    calls = _call(monkeypatch, responses)
    result = _run_tool(github_tools.github_create_branch, "feature/new-thing")
    assert "Successfully" in result
    checkouts = [c for c in calls if c[:2] == ["git", "checkout"]]
    assert checkouts, "expected a checkout for a valid branch name"
    assert ["git", "checkout", "-B", "feature/new-thing"] in checkouts
