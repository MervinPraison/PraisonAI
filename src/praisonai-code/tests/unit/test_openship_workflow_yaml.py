"""Validation tests for the OpenShip GitHub-native workflow templates and showcase folder."""

from pathlib import Path

import yaml

from praisonai_code.ship import onboard

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
    assert "@praisonai review" in raw
    assert "openship/review" in raw
    assert "openship/approvals" in raw
    assert "checks: read" in raw
    assert "actions: read" in raw
    assert 'git config user.name "openship[bot]"' in raw
    assert "is_fork == 'false'" in raw
    assert "pull_request_target" in triggers
    assert "CONFLICTING" in raw
    assert "secrets.OPENSHIP_GH_TOKEN || secrets.GITHUB_TOKEN" in raw
    assert "GH_REPO: ${{ github.repository }}" in raw
    assert "praisonai-code ship" in raw
    assert "praisonai-code steward" in raw
    assert "praisonai-code approvals" in raw
    assert "praisonai ship" not in raw
    assert "praisonai steward" not in raw
    assert "praisonai approvals" not in raw
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
    assert "GH_REPO: ${{ github.repository }}" in raw
    assert "praisonai-code steward" in raw
    assert "praisonai steward" not in raw


def test_onboard_templates_match_showcase_files() -> None:
    assert (WORKFLOWS_DIR / "openship.yml").read_text(encoding="utf-8") == onboard.OPENSHIP_WORKFLOW_YAML
    assert (OPENSHIP_DIR / "examples" / "approvals.yml").read_text(encoding="utf-8") == onboard.APPROVALS_POLICY_YAML


def test_products_openship_is_showcase_only_and_readme_covers_onboarding() -> None:
    assert not (OPENSHIP_DIR / "pyproject.toml").exists(), "products/openship/ should be showcase-only; code lives in praisonai-code"
    readme = (OPENSHIP_DIR / "README.md").read_text(encoding="utf-8")
    assert "pyproject.toml" not in readme
    assert "praisonai-code ship check" in readme
    assert "praisonai-code ship ui" in readme
    assert "praisonai-code ship init" in readme
    assert "workflows/openship.yml" in readme
