"""Tests for GitHub-native OpenShip review: inline PR comments, REVIEW.md guidelines, adversarial verification."""

import json
import subprocess

from praisonai_code.ship.orchestrate import post_inline_review, ship
from praisonai_code.ship.review import ReviewFinding, ReviewReport, load_review_guidelines, review_diff


def test_load_review_guidelines_prefers_origin_base():
    def fake_run(cmd, **kw):
        if cmd == ["git", "show", "origin/main:REVIEW.md"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="Always check SQL injection.\n", stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

    assert load_review_guidelines("main", run=fake_run) == "Always check SQL injection."


def test_review_diff_injects_guidelines_and_runs_adversarial_verifier():
    prompts = []
    replies = iter([
        ReviewReport(findings=[
            ReviewFinding(path="a.py", line=2, severity="important", title="Real bug", fix="guard None"),
            ReviewFinding(path="a.py", line=99, severity="nit", title="False positive", fix=""),
        ]),
        ReviewReport(findings=[
            ReviewFinding(path="a.py", line=2, severity="important", title="Real bug", fix="guard None"),
        ]),
    ])

    class FakeAgent:
        def chat(self, prompt, output_pydantic=None):
            prompts.append(prompt)
            return next(replies)

    findings = review_diff(
        "diff --git a/a.py b/a.py\n@@ -1 +1,2 @@\n+x = 1\n+y = None.strip()\n",
        effort="high",
        agent=FakeAgent(),
        guidelines="Check for None dereferences.",
        verify=True,
    )
    assert len(prompts) == 2
    assert "Check for None dereferences." in prompts[0]
    assert "adversarial code-review verifier" in prompts[1]
    assert len(findings) == 1 and findings[0].title == "Real bug"


def test_post_inline_review_uses_comment_event_never_approve():
    diff = (
        "diff --git a/src/auth.py b/src/auth.py\n"
        "--- a/src/auth.py\n"
        "+++ b/src/auth.py\n"
        "@@ -1,2 +1,4 @@\n"
        " def check():\n"
        "+    secret = 'hardcoded'\n"
        "+    return secret\n"
        "     pass\n"
    )
    findings = [
        ReviewFinding(path="src/auth.py", line=2, severity="important", title="Hard-coded secret", fix="use env var"),
        ReviewFinding(path="src/other.py", line=50, severity="nit", title="Outside hunk note", fix="cleanup"),
    ]
    api_calls = []

    def fake_run(cmd, **kw):
        if cmd[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(
                cmd, 0,
                stdout=json.dumps({"number": 77, "url": "https://github.com/o/r/pull/77", "headRefOid": "deadbeef"}),
                stderr="",
            )
        if cmd[:2] == ["gh", "api"]:
            api_calls.append((cmd, json.loads(kw["input"])))
            return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    ok = post_inline_review("77", findings, "high", diff, run=fake_run)
    assert ok and len(api_calls) == 1
    cmd, payload = api_calls[0]
    assert "repos/o/r/pulls/77/reviews" in cmd
    assert payload["event"] == "COMMENT"
    assert payload["commit_id"] == "deadbeef"
    assert len(payload["comments"]) == 1
    assert payload["comments"][0]["path"] == "src/auth.py" and payload["comments"][0]["line"] == 2
    assert "Outside hunk note" in payload["body"]


def test_ship_post_review_passes_diff_to_inline_review():
    diff = "diff --git a/a.py b/a.py\n@@ -0,0 +1,2 @@\n+x = 1\n+y = 2\n"
    api_payloads = []

    def fake_run(cmd, **kw):
        if cmd[:3] == ["gh", "pr", "diff"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=diff, stderr="")
        if cmd[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(
                cmd, 0,
                stdout=json.dumps({"number": 12, "url": "https://github.com/o/r/pull/12", "headRefOid": "cafebabe"}),
                stderr="",
            )
        if cmd[:2] == ["gh", "api"]:
            api_payloads.append(json.loads(kw["input"]))
            return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    res = ship(
        "12",
        post_review=True,
        run=fake_run,
        review_fn=lambda d, effort="high", llm=None: [
            ReviewFinding(path="a.py", line=2, severity="important", title="Bug", fix="fix")
        ],
    )
    assert res.posted_review and len(api_payloads) == 1
    assert api_payloads[0]["event"] == "COMMENT"
    assert api_payloads[0]["comments"][0]["line"] == 2
