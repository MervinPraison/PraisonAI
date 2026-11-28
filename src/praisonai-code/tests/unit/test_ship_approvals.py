"""``praisonai ship`` (S-7): declarative PR approvals policy engine (.praisonai/approvals.yml)."""

import json
import subprocess

import pytest

from praisonai_code.ship.approvals import (
    ApprovalPolicy,
    ApprovalRule,
    check_pr_policy,
    evaluate_policy,
    load_policy,
)
from praisonai_code.ship.flow import ShipRefused


VALID_YAML = """
mode: enforce
protected_paths:
  - .praisonai/approvals.yml
  - .github/workflows/**
rules:
  - name: python-core
    paths: ["src/**/*.py"]
    seats: 2
    reviewers: ["alice", "bob", "carol"]
    checks: ["CI/test", "lint"]
  - name: docs
    paths: ["docs/**"]
    seats: 1
"""


def test_load_policy_parses_defaults_and_rules():
    p = load_policy(VALID_YAML)
    assert isinstance(p, ApprovalPolicy) and p.mode == "enforce"
    assert len(p.rules) == 2 and p.rules[0].seats == 2 and p.rules[0].checks == ["CI/test", "lint"]

    minimal = load_policy("rules:\n  - name: all\n")
    assert minimal.mode == "observe"
    assert ".praisonai/approvals.yml" in minimal.protected_paths
    assert minimal.rules[0] == ApprovalRule(name="all")


@pytest.mark.parametrize(
    "bad",
    [
        "not: [valid: yaml",
        "- a list, not a mapping",
        "mode: strict\nrules: []\n",
        "rules: not-a-list\n",
        "rules:\n  - seats: 1\n",  # missing name
        "rules:\n  - name: bad-seats\n    seats: true\n",
        "rules:\n  - name: neg\n    seats: -1\n",
    ],
)
def test_load_policy_rejects_invalid_yaml_or_schema(bad):
    with pytest.raises(ValueError):
        load_policy(bad)


def test_evaluate_glob_matching_seats_reviewers_and_checks():
    policy = load_policy(VALID_YAML)

    # Only 1 eligible approver (dave is not in reviewers), missing lint check
    rep = evaluate_policy(
        policy,
        changed_files=["src/pkg/mod.py"],
        approvers=["Alice", "dave"],
        passing_checks=["CI/test"],
    )
    assert not rep.passed and rep.blocking
    assert len(rep.verdicts) == 1 and rep.verdicts[0].rule == "python-core"
    assert any("2" in r for r in rep.verdicts[0].reasons)
    assert any("lint" in r for r in rep.verdicts[0].reasons)

    # 2 distinct eligible approvers + all checks pass
    ok = evaluate_policy(
        policy,
        changed_files=["src/a.py"],
        approvers=["Alice", "alice", "BOB"],
        passing_checks=["CI/test", "lint"],
    )
    assert ok.passed and not ok.blocking


def test_observe_mode_reports_failure_without_blocking():
    policy = load_policy("mode: observe\nrules:\n  - name: all\n    seats: 2\n")
    rep = evaluate_policy(policy, changed_files=["README.md"], approvers=["alice"])
    assert not rep.passed and not rep.blocking and rep.mode == "observe"


def test_protected_paths_require_human_approval_even_when_rules_pass():
    policy = load_policy("mode: enforce\nrules:\n  - name: all\n    seats: 0\n")

    # No approver (or bot-only approver) fails on protected workflow file
    rep_none = evaluate_policy(policy, changed_files=[".github/workflows/ci.yml"], approvers=[])
    assert not rep_none.passed and rep_none.blocking
    assert rep_none.protected_touched == [".github/workflows/ci.yml"]

    rep_bot = evaluate_policy(policy, changed_files=[".praisonai/approvals.yml"], approvers=["dependabot[bot]"])
    assert not rep_bot.passed and rep_bot.blocking

    # Human approver satisfies protected_paths
    rep_human = evaluate_policy(policy, changed_files=[".github/workflows/ci.yml"], approvers=["mervin"])
    assert rep_human.passed and not rep_human.blocking


def test_check_pr_policy_loads_strictly_from_base_branch_and_uses_latest_review():
    view = {
        "number": 12,
        "baseRefName": "main",
        "files": [{"path": "src/a.py"}],
        "reviews": [
            {"author": {"login": "alice"}, "state": "APPROVED"},
            {"author": {"login": "alice"}, "state": "COMMENTED"},  # does not revoke approval
            {"author": {"login": "bob"}, "state": "APPROVED"},
            {"author": {"login": "bob"}, "state": "CHANGES_REQUESTED"},  # revokes bob's approval
            {"author": {"login": "carol"}, "state": "APPROVED"},
            {"author": {"login": "carol"}, "state": "DISMISSED"},  # revokes carol's approval
        ],
        "statusCheckRollup": [
            {"__typename": "CheckRun", "workflowName": "CI", "name": "test", "conclusion": "SUCCESS"},
            {"__typename": "CheckRun", "name": "lint", "conclusion": "SUCCESS"},
        ],
    }
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(view), stderr="")
        if cmd[:2] == ["git", "show"] and cmd[2] == "origin/main:.praisonai/approvals.yml":
            return subprocess.CompletedProcess(cmd, 0, stdout=VALID_YAML, stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="not found")

    rep = check_pr_policy("#12", run=fake_run)
    # Must read policy from origin/main, never head
    assert ["git", "show", "origin/main:.praisonai/approvals.yml"] in calls
    assert not any("HEAD" in " ".join(c) for c in calls)
    # Only alice remains APPROVED (bob requested changes, carol dismissed) -> needs 2 seats -> fails
    assert not rep.passed and rep.blocking


def test_check_pr_policy_falls_back_to_local_base_and_refuses_when_missing():
    view = {"number": 12, "baseRefName": "main", "files": [{"path": "docs/x.md"}], "reviews": [{"author": {"login": "alice"}, "state": "APPROVED"}], "statusCheckRollup": []}

    def fallback_run(cmd, **kw):
        if cmd[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(view), stderr="")
        if cmd == ["git", "show", "main:.praisonai/approvals.yml"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=VALID_YAML, stderr="")
        return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="missing")

    assert check_pr_policy("12", run=fallback_run).passed

    def missing_run(cmd, **kw):
        if cmd[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(view), stderr="")
        return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="missing")

    with pytest.raises(ShipRefused, match="approvals.yml"):
        check_pr_policy("12", run=missing_run)
