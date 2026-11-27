"""Validation tests for the OpenShip GitHub-native workflow templates and showcase folder."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
OPENSHIP_DIR = REPO_ROOT / "products" / "openship"
WORKFLOWS_DIR = OPENSHIP_DIR / "workflows"


def test_openship_full_github_workflow_covers_all_three_pillars() -> None:
    wf_path = WORKFLOWS_DIR / "openship.yml"
    assert wf_path.is_file()
    raw = wf_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    assert isinstance(data, dict)

    # PyYAML parses bare `on:` as boolean True
    triggers = data.get("on") or data.get(True)
    assert isinstance(triggers, dict)
    for required in ("pull_request", "pull_request_review", "pull_request_review_comment", "issue_comment", "workflow_run"):
        assert required in triggers, f"openship.yml missing trigger {required!r}"

    jobs = data["jobs"]
    assert {"review", "steward", "approvals"}.issubset(jobs.keys())
    assert "openship-stop" in raw
    assert "@praisonai stop" in raw
    assert "is_fork == 'false'" in raw
    assert "gh pr merge" not in raw
    assert "--approve" not in raw
    assert "--force" not in raw


def test_steward_workflow_triggers_on_ci_failure_and_mentions() -> None:
    wf_path = WORKFLOWS_DIR / "steward.yml"
    raw = wf_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    triggers = data.get("on") or data.get(True)
    assert "workflow_run" in triggers
    assert "issue_comment" in triggers
    assert "pull_request_review_comment" in triggers
    assert "openship-stop" in raw


def test_products_openship_is_showcase_only_no_separate_package() -> None:
    assert not (OPENSHIP_DIR / "pyproject.toml").exists(), "products/openship/ should be showcase-only; code lives in praisonai-code"
