"""``praisonai ship`` (S-5): full orchestration (flow -> review -> optional watch) and CLI."""

import subprocess

import pytest
from typer.testing import CliRunner

from praisonai_code.ship import ShipResult, ship
from praisonai_code.ship import flow
from praisonai_code.ship.flow import ShipRefused
from praisonai_code.ship.review import ReviewFinding


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    monkeypatch.delenv("PRAISONAI_DISABLE_SHIP", raising=False)
    monkeypatch.delenv("PRAISONAI_SHIP_ENABLED", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / ".praisonai"))


class FakeRun:
    def __init__(self, diff="diff --git a/a.py b/a.py\n+x = 1\n"):
        self.diff = diff
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        if cmd[:3] == ["gh", "pr", "diff"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=self.diff, stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    def ran(self, *prefix):
        return [c for c in self.calls if tuple(c[: len(prefix)]) == prefix]


def test_dry_run_returns_plan_without_review_or_watch(monkeypatch):
    monkeypatch.setattr(flow, "ship_to_draft_pr", lambda **kw: "Would commit on 'feat/x'")
    res = ship(
        dry_run=True,
        review_fn=lambda *a, **kw: (_ for _ in ()).throw(AssertionError("must not review on dry-run")),
        watch_fn=lambda *a, **kw: (_ for _ in ()).throw(AssertionError("must not watch on dry-run")),
    )
    assert isinstance(res, ShipResult)
    assert res.pr_url == "" and "Would commit" in res.dry_run_plan
    assert res.findings == [] and res.severity == "none" and not res.watched


def test_disabled_raises_ship_refused_before_any_work(monkeypatch):
    monkeypatch.setenv("PRAISONAI_DISABLE_SHIP", "1")
    monkeypatch.setattr(
        flow, "ship_to_draft_pr", lambda **kw: (_ for _ in ()).throw(AssertionError("must not run"))
    )
    with pytest.raises(ShipRefused, match="PRAISONAI_DISABLE_SHIP"):
        ship()


def test_full_local_branch_flow_reviews_pr_and_forwards_model(monkeypatch):
    flow_seen, rev_seen = {}, {}

    def fake_flow(**kw):
        flow_seen.update(kw)
        return "https://github.com/o/r/pull/9"

    def fake_review(diff, effort="high", llm=None):
        rev_seen.update(diff=diff, effort=effort, llm=llm)
        return [ReviewFinding(path="a.py", line=2, severity="important", title="bug", fix="fix it")]

    monkeypatch.setattr(flow, "ship_to_draft_pr", fake_flow)
    run = FakeRun()
    res = ship(message="feat: x", effort="medium", model="ollama/llama3.2", run=run, review_fn=fake_review)
    assert flow_seen["llm"] == "ollama/llama3.2" and flow_seen["message"] == "feat: x"
    assert rev_seen["effort"] == "medium" and rev_seen["llm"] == "ollama/llama3.2"
    assert "+x = 1" in rev_seen["diff"]
    assert res.pr_url == "https://github.com/o/r/pull/9" and res.severity == "high"
    assert len(res.findings) == 1 and not res.posted_review


def test_post_review_posts_markdown_comment_and_skips_when_empty(monkeypatch):
    monkeypatch.setattr(flow, "ship_to_draft_pr", lambda **kw: "https://github.com/o/r/pull/9")
    finding = ReviewFinding(path="a.py", line=5, severity="important", title="null deref", fix="check None")

    run1 = FakeRun()
    res1 = ship(post_review=True, run=run1, review_fn=lambda *a, **kw: [finding])
    assert res1.posted_review
    comment = run1.ran("gh", "pr", "comment")[0]
    body = comment[comment.index("--body") + 1]
    assert "a.py:5" in body and "null deref" in body and "check None" in body

    run2 = FakeRun()
    res2 = ship(post_review=True, run=run2, review_fn=lambda *a, **kw: [])
    assert not res2.posted_review and not run2.ran("gh", "pr", "comment")


def test_target_pr_number_skips_flow_and_reviews_directly(monkeypatch):
    monkeypatch.setattr(
        flow, "ship_to_draft_pr", lambda **kw: (_ for _ in ()).throw(AssertionError("must skip flow"))
    )
    run = FakeRun()
    res = ship("42", run=run, review_fn=lambda *a, **kw: [])
    assert res.pr_url == "42" and run.ran("gh", "pr", "diff", "42")


def test_target_plus_reviewer_ships_and_requests_reviewer(monkeypatch):
    monkeypatch.setattr(flow, "ship_to_draft_pr", lambda **kw: "https://github.com/o/r/pull/9")
    run = FakeRun()
    res = ship("+copilot", review=False, run=run)
    assert res.reviewer == "copilot"
    assert run.ran("gh", "pr", "edit", "https://github.com/o/r/pull/9", "--add-reviewer", "copilot")


def test_watch_true_hands_off_to_watch_fn(monkeypatch):
    monkeypatch.setattr(flow, "ship_to_draft_pr", lambda **kw: "https://github.com/o/r/pull/9")
    watched = {}

    def fake_watch(pr, **kw):
        watched["pr"] = pr
        watched.update(kw)

    res = ship(review=False, watch=True, model="gpt-4o-mini", run=FakeRun(), watch_fn=fake_watch)
    assert res.watched and watched["pr"] == "https://github.com/o/r/pull/9" and watched["llm"] == "gpt-4o-mini"


def test_unrecognized_target_raises_ship_refused():
    with pytest.raises(ShipRefused, match="unrecognized target"):
        ship("not-a-pr")


def test_cli_help_and_options_forward_to_ship(monkeypatch):
    from praisonai_code.cli.commands import ship as ship_cmd
    from praisonai_code.ship import orchestrate

    help_res = CliRunner().invoke(ship_cmd.app, ["--help"])
    assert help_res.exit_code == 0
    for flag in ("--effort", "--model", "--post-review", "--watch", "--reviewer", "--dry-run"):
        assert flag in help_res.output

    seen = {}

    def fake_ship(target=None, **kw):
        seen["target"] = target
        seen.update(kw)
        return ShipResult(pr_url="https://github.com/o/r/pull/42", findings=[], severity="none")

    monkeypatch.setattr(orchestrate, "ship", fake_ship)
    res = CliRunner().invoke(ship_cmd.app, ["42", "--effort", "low", "--model", "gpt-4o-mini", "--post-review"])
    assert res.exit_code == 0 and "pull/42" in res.output
    assert seen["target"] == "42" and seen["effort"] == "low"
    assert seen["model"] == "gpt-4o-mini" and seen["post_review"] is True
