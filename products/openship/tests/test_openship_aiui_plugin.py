"""Tests for the OpenShip PraisonAIUI plugin (contract, routes, auth modes, safety guards)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from starlette.testclient import TestClient

import praisonaiui as aiui
from praisonaiui import server as aiui_server
from praisonaiui.server import create_app

from praisonai_ship_ui import OpenShipPlugin, plugin, service

PKG_DIR = Path(__file__).resolve().parents[1] / "praisonai_ship_ui"


@pytest.fixture()
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    aiui_server.reset_state()
    monkeypatch.setenv("AIUI_DATA_DIR", str(tmp_path / "aiui-data"))
    monkeypatch.setenv("OPENSHIP_LEDGER_PATH", str(tmp_path / "runs.jsonl"))
    monkeypatch.setenv("OPENSHIP_REPO", str(tmp_path))
    monkeypatch.setenv("AIUI_DISABLE_PLUGIN_AUTOLOAD", "1")
    yield tmp_path
    aiui_server.reset_state()


def test_plugin_contract_and_no_shadowed_builtin_ids() -> None:
    p = OpenShipPlugin()
    assert p.name == "openship"
    assert p.sdk == 1
    page_ids = [spec.id for spec in p.pages()]
    assert page_ids == ["openship", "openship-review", "openship-steward", "openship-policy"]
    assert all(spec.kind == "blocks" for spec in p.pages())
    assert [g.name for g in p.nav_groups()] == ["OpenShip"]
    assert [s.id for s in p.settings()] == ["defaults"]
    assert len(p.routes()) == 8

    # Ensure zero collision with PraisonAIUI built-in page IDs (including builtin.approvals)
    from praisonaiui.builtin.catalog import BUILTIN_PLUGINS

    builtin_ids = set()
    for rec in BUILTIN_PLUGINS:
        pages_obj = rec.pages() if callable(rec.pages) else rec.pages
        for bp in pages_obj:
            builtin_ids.add(bp.id)
    assert set(page_ids).isdisjoint(builtin_ids)


def test_never_merge_approve_or_force_push_ast_guard() -> None:
    """Static guard: no file in praisonai_ship_ui may invoke merge, approve, or force-push."""
    forbidden = ("pr merge", "--approve", "--force", "force-with-lease", "shell=True")
    for py_file in PKG_DIR.rglob("*.py"):
        src = py_file.read_text(encoding="utf-8")
        ast.parse(src)
        for token in forbidden:
            assert token not in src, f"Forbidden token {token!r} found in {py_file}"


def test_split_unified_diff_and_pr_validation() -> None:
    diff = (
        "diff --git a/src/app.py b/src/app.py\n"
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1,2 +1,3 @@\n"
        " x = 1\n"
        "-y = 2\n"
        "+y = 3\n"
        "+z = 4\n"
    )
    files = service.split_unified_diff(diff)
    assert len(files) == 1
    assert files[0].path == "src/app.py"
    assert files[0].before == "x = 1\ny = 2"
    assert files[0].after == "x = 1\ny = 3\nz = 4"

    assert service.normalize_pr("#6852") == "6852"
    assert service.normalize_pr("  42 ") == "42"
    assert service.normalize_pr("") is None
    with pytest.raises(ValueError):
        service.normalize_pr("6852; rm -rf /")


def test_policy_path_blocks_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        service.resolve_policy_path(tmp_path, "../../etc/passwd")


def test_write_actions_require_explicit_confirmation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Confirmation required"):
        service.create_draft_pr(tmp_path, confirm=False)
    with pytest.raises(ValueError, match="Confirmation required"):
        service.post_review_comment(tmp_path, pr="6852", findings=[], severity="none", confirm=False)
    with pytest.raises(ValueError, match="Confirmation required"):
        service.run_steward_once(tmp_path, pr="6852", confirm=False)


def test_routes_end_to_end_and_confirmation_gate(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        service,
        "get_repo_status",
        lambda repo, run=None: service.RepoStatus(repo=str(repo), branch="feat/demo", base="main", gh_ready=True),
    )
    monkeypatch.setattr(
        service,
        "list_prs",
        lambda repo, limit=12, run=None: (
            [{"number": 6852, "title": "Add approvals CLI", "state": "MERGED", "isDraft": False, "headRefName": "feat/approvals"}],
            "",
        ),
    )
    monkeypatch.setattr(
        service,
        "get_diff_bundle",
        lambda repo, pr=None, run=None: (
            "diff --git a/a.py b/a.py\n+x = 1\n",
            [service.FileDiff("a.py", "", "x = 1")],
            "working branch",
        ),
    )
    monkeypatch.setattr(service, "run_dry_run", lambda repo, pr=None, run=None: "Would commit on 'feat/demo'")
    monkeypatch.setattr(
        service,
        "run_review",
        lambda repo, **kw: {
            "source": "working branch",
            "pr": None,
            "model": "gpt-4o-mini",
            "severity": "high",
            "findings": [{"path": "a.py", "line": 1, "severity": "important", "title": "Demo bug", "fix": "Fix it"}],
            "diff": "+x = 1",
            "files": [service.FileDiff("a.py", "", "x = 1")],
        },
    )
    monkeypatch.setattr(
        service,
        "inspect_steward",
        lambda repo, pr=None, max_attempts=3, run=None: {
            "number": 6852,
            "url": "https://github.com/MervinPraison/PraisonAI/pull/6852",
            "state": "MERGED",
            "mergeable": "UNKNOWN",
            "head": "feat/approvals",
            "base": "main",
            "failing": [],
            "threads": [],
            "next_action": {"kind": "stop", "key": "", "detail": "pull request is merged"},
            "max_attempts": 3,
        },
    )
    monkeypatch.setattr(
        service,
        "evaluate_pr_policy",
        lambda repo, pr=None, policy_path=None, run=None: {
            "pr": pr or "6852",
            "passed": False,
            "mode": "observe",
            "blocking": False,
            "summary": "failed (observe): core-source",
            "protected_touched": [],
            "verdicts": [{"rule": "core-source", "passed": False, "reasons": ["needs 1 approval"]}],
            "policy_yaml": "mode: observe\n",
        },
    )

    aiui.set_style("app")
    aiui.register_plugin(plugin)
    aiui.only_my_pages()
    app = create_app()

    with TestClient(app) as client:
        # Manifest lists ONLY our 4 OpenShip pages
        manifest = client.get("/api/shell/manifest").json()
        page_ids = [p["id"] for p in manifest["pages"]]
        assert page_ids == ["openship", "openship-review", "openship-steward", "openship-policy"]

        # GET all 4 pages return valid _components block trees
        for pid in page_ids:
            r = client.get(f"/api/plugins/openship/pages/{pid}", params={"pr": "6852"})
            assert r.status_code == 200, f"{pid}: {r.text}"
            data = r.json()
            assert "_components" in data and len(data["_components"]) >= 3

        # POST dry-run + review succeed
        r_dry = client.post("/api/plugins/openship/pages/openship-review/action", json={"action": "dry_run"})
        assert r_dry.status_code == 200
        assert "Dry-run plan ready" in r_dry.json()["message"]

        # POST review with FormBlock-style payload (no "action" field, matching collectFormValues)
        r_rev = client.post(
            "/api/plugins/openship/pages/openship-review/action",
            json={"pr": "", "effort": "low", "model": "gpt-4o-mini"},
        )
        assert r_rev.status_code == 200
        assert "1 finding(s)" in r_rev.json()["message"]

        # POST write action without confirm=True MUST be rejected (400) — FormBlock payload (no "action")
        r_unconfirmed = client.post(
            "/api/plugins/openship/pages/openship-review/action",
            json={"write_op": "ship_draft", "message": "", "confirm": False},
        )
        assert r_unconfirmed.status_code == 400
        assert "Confirmation required" in r_unconfirmed.json()["error"]

        r_steward_unconfirmed = client.post(
            "/api/plugins/openship/pages/openship-steward/action",
            json={"pr": "6852", "model": "", "confirm": False},
        )
        assert r_steward_unconfirmed.status_code == 400

        # POST policy evaluation succeeds
        r_pol = client.post(
            "/api/plugins/openship/pages/openship-policy/action",
            json={"action": "evaluate_policy", "pr": "6852"},
        )
        assert r_pol.status_code == 200
        assert "failed (observe)" in r_pol.json()["message"]


def test_plugin_routes_protected_under_token_auth(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """R8: Plugin routes deny unauthenticated requests under AIUI_REQUIRE_TOKEN."""
    monkeypatch.setenv("AIUI_REQUIRE_TOKEN", "1")
    monkeypatch.setenv("GATEWAY_AUTH_TOKEN", "test-secret-token-xyz")
    monkeypatch.setattr(
        service,
        "get_repo_status",
        lambda repo, run=None: service.RepoStatus(repo=str(repo), branch="main", base="main"),
    )
    monkeypatch.setattr(service, "list_prs", lambda repo, limit=12, run=None: ([], ""))

    aiui.set_style("app")
    aiui.register_plugin(plugin)
    aiui.only_my_pages()
    app = create_app()

    with TestClient(app) as client:
        unauth = client.get("/api/plugins/openship/pages/openship")
        assert unauth.status_code in (401, 403)
        authed = client.get(
            "/api/plugins/openship/pages/openship",
            headers={"Authorization": "Bearer test-secret-token-xyz"},
        )
        assert authed.status_code == 200
