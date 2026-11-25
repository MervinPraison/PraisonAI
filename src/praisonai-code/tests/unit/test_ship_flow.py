"""``praisonai ship`` step 1: commit, push and open a draft PR. Never merge."""

import json
import subprocess

import pytest

from praisonai_code.ship.flow import ShipRefused, ship_to_draft_pr


class FakeRunner:
    """Answers git/gh calls from a table and records every call."""

    def __init__(self, *, branch="feat/x", default="main", fork=False, status="", pr=None, gh_ok=True):
        self.calls = []
        self.answers = {
            ("git", "rev-parse"): branch,
            ("git", "status"): status,
            ("git", "diff"): "diff --git a/a.py b/a.py\n+x = 1\n",
            ("gh", "repo"): json.dumps({"defaultBranchRef": {"name": default}, "isFork": fork}) if gh_ok else None,
            ("gh", "pr", "view"): json.dumps({"url": pr, "state": "OPEN"}) if pr else None,
            ("gh", "pr", "create"): "https://github.com/o/r/pull/9\n",
        }

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        key = next((k for k in self.answers if tuple(cmd[: len(k)]) == k), None)
        out = self.answers.get(key, "") if key else ""
        code = 1 if out is None else 0
        return subprocess.CompletedProcess(cmd, code, stdout=out or "", stderr="")

    def ran(self, *prefix):
        return [c for c in self.calls if tuple(c[: len(prefix)]) == prefix]


def test_refuses_on_the_default_branch():
    with pytest.raises(ShipRefused, match="default branch"):
        ship_to_draft_pr(run=FakeRunner(branch="main"))


def test_refuses_a_fork():
    with pytest.raises(ShipRefused, match="fork"):
        ship_to_draft_pr(run=FakeRunner(fork=True))


def test_refuses_without_a_github_repo():
    with pytest.raises(ShipRefused, match="GitHub"):
        ship_to_draft_pr(run=FakeRunner(gh_ok=False))


def test_refuses_to_commit_a_secret_file():
    run = FakeRunner(status=" M a.py\0?? config/.env\0")
    with pytest.raises(ShipRefused, match=r"config/\.env"):
        ship_to_draft_pr(run=run)
    assert not run.ran("git", "commit")


def test_example_env_file_is_not_a_secret():
    run = FakeRunner(status="?? .env.example\0")
    assert ship_to_draft_pr(message="docs: env example", run=run) == "https://github.com/o/r/pull/9"


def test_commits_pushes_and_opens_a_draft_pr():
    run = FakeRunner(status=" M a.py\0")
    url = ship_to_draft_pr(message="feat: x", run=run)
    assert url == "https://github.com/o/r/pull/9"
    assert run.ran("git", "add", "-A")
    assert run.ran("git", "commit", "-m", "feat: x")
    assert run.ran("git", "push", "-u", "origin", "HEAD")
    create = run.ran("gh", "pr", "create")[0]
    assert "--draft" in create and create[create.index("--base") + 1] == "main"


def test_generates_a_message_when_none_is_given():
    run = FakeRunner(status=" M a.py\0")
    ship_to_draft_pr(run=run)
    message = run.ran("git", "commit")[0][-1]
    assert message.strip()


def test_clean_tree_skips_the_commit_and_reuses_an_open_pr():
    run = FakeRunner(pr="https://github.com/o/r/pull/3")
    assert ship_to_draft_pr(run=run) == "https://github.com/o/r/pull/3"
    assert not run.ran("git", "commit")
    assert not run.ran("gh", "pr", "create")
    assert run.ran("git", "push")


def test_dry_run_writes_nothing():
    run = FakeRunner(status=" M a.py\0")
    plan = ship_to_draft_pr(dry_run=True, run=run)
    assert "feat/x" in plan and "main" in plan and "a.py" in plan
    for verb in (("git", "add"), ("git", "commit"), ("git", "push"), ("gh", "pr", "create")):
        assert not run.ran(*verb)


def test_never_merges_or_force_pushes():
    run = FakeRunner(status=" M a.py\0")
    ship_to_draft_pr(message="feat: x", run=run)
    flat = [" ".join(c) for c in run.calls]
    assert not any("merge" in c.split()[:3] or "--force" in c or " -f" in c for c in flat)


def test_rename_lists_the_new_path_only():
    run = FakeRunner(status="R  new.py\0old.env\0")
    assert "new.py" in ship_to_draft_pr(dry_run=True, run=run)


def test_cli_prints_the_refusal_and_exits_1(monkeypatch):
    from typer.testing import CliRunner

    from praisonai_code.cli.commands import ship as ship_cmd
    from praisonai_code.ship import flow

    def refuse(**kwargs):
        raise flow.ShipRefused("on the default branch 'main'")

    monkeypatch.setattr(flow, "ship_to_draft_pr", refuse)
    result = CliRunner().invoke(ship_cmd.app, ["--dry-run"])
    assert result.exit_code == 1
    assert "default branch" in result.output


def test_ship_is_a_registered_command():
    from praisonai_code.cli import app as cli_app

    assert cli_app._LAZY_COMMANDS["ship"][0] == ".commands.ship"
