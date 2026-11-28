"""``praisonai ship`` step 1: commit, push and open a draft PR. Never merge."""

import json
import subprocess

import pytest

from praisonai_code.ship import pr_text
from praisonai_code.ship.flow import ShipRefused, ship_to_draft_pr

_REAL_WRITE_PR_TEXT = pr_text.write_pr_text


@pytest.fixture(autouse=True)
def _stub_pr_text(monkeypatch):
    """Avoid network/LLM calls in flow unit tests unless a test exercises write_pr_text directly."""
    monkeypatch.setattr(
        pr_text,
        "write_pr_text",
        lambda commits, diff: pr_text.PRText(
            title=commits[0], body="\n".join(f"- {c}" for c in commits)
        ),
    )


class FakeRunner:
    """Answers git/gh calls from a table and records every call."""

    def __init__(
        self,
        *,
        branch="feat/x",
        default="main",
        fork=False,
        status="",
        pr=None,
        gh_ok=True,
        commits=("feat: x",),
        origin_base=True,
    ):
        self.calls = []
        log_out = "\n".join(commits) + ("\n" if commits else "")
        self.answers = {
            ("git", "rev-parse"): branch,
            ("git", "status"): status,
            ("git", "log", "--reverse", "--format=%s", f"origin/{default}..HEAD"): log_out if origin_base else None,
            ("git", "log"): log_out,
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


def test_draft_pr_uses_write_pr_text_title_and_body_not_fill(monkeypatch):
    seen = {}

    def fake_write(commits, diff):
        seen["commits"] = commits
        seen["diff"] = diff
        return pr_text.PRText(title="Add feature X", body="What changed and why.")

    monkeypatch.setattr(pr_text, "write_pr_text", fake_write)
    run = FakeRunner(commits=("feat: first", "test: second"))
    url = ship_to_draft_pr(run=run)
    assert url == "https://github.com/o/r/pull/9"
    assert seen["commits"] == ["feat: first", "test: second"]
    assert "+x = 1" in seen["diff"]
    assert run.ran("git", "log", "--reverse", "--format=%s", "origin/main..HEAD")
    assert run.ran("git", "diff", "origin/main...HEAD")
    create = run.ran("gh", "pr", "create")[0]
    assert "--fill" not in create
    assert "--draft" in create
    assert create[create.index("--title") + 1] == "Add feature X"
    assert create[create.index("--body") + 1] == "What changed and why."


def test_falls_back_to_local_base_ref_when_origin_base_is_missing():
    run = FakeRunner(origin_base=False, commits=("fix: local ref",))
    assert ship_to_draft_pr(run=run) == "https://github.com/o/r/pull/9"
    assert run.ran("git", "log", "--reverse", "--format=%s", "main..HEAD")
    assert run.ran("git", "diff", "main...HEAD")
    create = run.ran("gh", "pr", "create")[0]
    assert "--fill" not in create
    assert create[create.index("--title") + 1] == "fix: local ref"


def test_refuses_when_no_commits_ahead_of_base(monkeypatch):
    called = []
    monkeypatch.setattr(pr_text, "write_pr_text", lambda c, d: called.append((c, d)))
    run = FakeRunner(commits=())
    with pytest.raises(ShipRefused, match="no commits"):
        ship_to_draft_pr(run=run)
    assert not called
    assert not run.ran("gh", "pr", "create")


def test_dry_run_does_not_call_write_pr_text(monkeypatch):
    def boom(commits, diff):
        raise AssertionError("write_pr_text must not run during --dry-run")

    monkeypatch.setattr(pr_text, "write_pr_text", boom)
    plan = ship_to_draft_pr(dry_run=True, run=FakeRunner(status=" M a.py\0"))
    assert "feat/x" in plan and "a.py" in plan


def test_existing_open_pr_does_not_call_write_pr_text(monkeypatch):
    def boom(commits, diff):
        raise AssertionError("write_pr_text must not run when an open PR already exists")

    monkeypatch.setattr(pr_text, "write_pr_text", boom)
    assert ship_to_draft_pr(run=FakeRunner(pr="https://github.com/o/r/pull/3")) == "https://github.com/o/r/pull/3"


def test_model_failure_falls_back_to_commit_list_in_pr_create(monkeypatch):
    import praisonaiagents

    monkeypatch.setattr(pr_text, "write_pr_text", _REAL_WRITE_PR_TEXT)

    class _DownAgent:
        def __init__(self, **kwargs):
            raise RuntimeError("offline")

    monkeypatch.setattr(praisonaiagents, "Agent", _DownAgent)
    run = FakeRunner(commits=("feat: a", "fix: b"))
    assert ship_to_draft_pr(run=run) == "https://github.com/o/r/pull/9"
    create = run.ran("gh", "pr", "create")[0]
    assert "--fill" not in create
    assert create[create.index("--title") + 1] == "feat: a"
    assert create[create.index("--body") + 1] == "- feat: a\n- fix: b"
