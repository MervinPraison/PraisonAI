"""Tests for the OpenShip PraisonAIUI plugin inside praisonai-code."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from praisonai_code.ship import ui_service as service

SHIP_DIR = Path(__file__).resolve().parents[2] / "praisonai_code" / "ship"


def test_never_merge_approve_or_force_push_ast_guard() -> None:
    """Static guard: UI modules may never invoke merge, approve, force-push, or shell=True."""
    forbidden = ("pr merge", "--approve", "--force", "force-with-lease", "shell=True")
    for name in ("ui_service.py", "ui_plugin.py"):
        src = (SHIP_DIR / name).read_text(encoding="utf-8")
        ast.parse(src)
        for token in forbidden:
            assert token not in src, f"Forbidden token {token!r} found in {name}"


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


def test_ledger_append_and_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENSHIP_LEDGER_PATH", str(tmp_path / "runs.jsonl"))
    service.append_ledger({"kind": "review", "pr": "6852", "important": 2, "nit": 1, "severity": "high"})
    service.append_ledger({"kind": "policy", "pr": "6852", "passed": True, "mode": "observe"})
    summary = service.summarize_ledger(service.load_ledger())
    assert summary["total_reviews"] == 1
    assert summary["important_caught"] == 2
    assert summary["policy_pass_rate"] == "100%"


def test_plugin_contract_and_no_shadowed_builtin_ids() -> None:
    pytest.importorskip("praisonaiui")
    from praisonaiui.builtin.catalog import BUILTIN_PLUGINS
    from praisonai_code.ship.ui_plugin import OpenShipPlugin

    p = OpenShipPlugin()
    assert p.name == "openship"
    assert p.sdk == 1
    page_ids = [spec.id for spec in p.pages()]
    assert page_ids == ["openship", "openship-review", "openship-steward", "openship-policy"]
    assert all(spec.kind == "blocks" for spec in p.pages())
    assert [g.name for g in p.nav_groups()] == ["OpenShip"]
    assert [s.id for s in p.settings()] == ["defaults"]
    assert len(p.routes()) == 8

    builtin_ids = set()
    for rec in BUILTIN_PLUGINS:
        pages_obj = rec.pages() if callable(rec.pages) else rec.pages
        for bp in pages_obj:
            builtin_ids.add(bp.id)
    assert set(page_ids).isdisjoint(builtin_ids)


def test_routes_end_to_end_and_confirmation_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    aiui = pytest.importorskip("praisonaiui")
    from starlette.testclient import TestClient
    from praisonaiui import server as aiui_server
    from praisonaiui.server import create_app
    from praisonai_code.ship.ui_plugin import plugin

    aiui_server.reset_state()
    monkeypatch.setenv("AIUI_DATA_DIR", str(tmp_path / "aiui-data"))
    monkeypatch.setenv("OPENSHIP_LEDGER_PATH", str(tmp_path / "runs.jsonl"))
    monkeypatch.setenv("OPENSHIP_REPO", str(tmp_path))
    monkeypatch.setenv("AIUI_DISABLE_PLUGIN_AUTOLOAD", "1")

    monkeypatch.setattr(service, "get_repo_status", lambda repo, run=None: service.RepoStatus(repo=str(repo), branch="feat/demo", base="main", gh_ready=True))
    monkeypatch.setattr(service, "list_prs", lambda repo, limit=12, run=None: ([{"number": 6852, "title": "Add approvals CLI", "state": "MERGED", "isDraft": False, "headRefName": "feat/approvals"}], ""))
    monkeypatch.setattr(service, "get_diff_bundle", lambda repo, pr=None, run=None: ("diff --git a/a.py b/a.py\n+x = 1\n", [service.FileDiff("a.py", "", "x = 1")], "working branch"))
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

    try:
        aiui.set_style("app")
        aiui.register_plugin(plugin)
        aiui.only_my_pages()
        with TestClient(create_app()) as client:
            manifest = client.get("/api/shell/manifest").json()
            page_ids = [p["id"] for p in manifest["pages"]]
            assert page_ids == ["openship", "openship-review", "openship-steward", "openship-policy"]

            for pid in page_ids:
                r = client.get(f"/api/plugins/openship/pages/{pid}", params={"pr": "6852"})
                assert r.status_code == 200
                assert len(r.json()["_components"]) >= 3

            r_dry = client.post("/api/plugins/openship/pages/openship-review/action", json={"action": "dry_run"})
            assert r_dry.status_code == 200

            # FormBlock payload (no "action" key, matching collectFormValues)
            r_rev = client.post("/api/plugins/openship/pages/openship-review/action", json={"pr": "", "effort": "low", "model": "gpt-4o-mini"})
            assert r_rev.status_code == 200
            assert "1 finding(s)" in r_rev.json()["message"]

            # Unconfirmed write actions MUST fail with 400
            assert client.post("/api/plugins/openship/pages/openship-review/action", json={"write_op": "ship_draft", "confirm": False}).status_code == 400
            assert client.post("/api/plugins/openship/pages/openship-steward/action", json={"pr": "6852", "confirm": False}).status_code == 400

            r_pol = client.post("/api/plugins/openship/pages/openship-policy/action", json={"pr": "6852"})
            assert r_pol.status_code == 200
            assert "failed (observe)" in r_pol.json()["message"]
    finally:
        aiui_server.reset_state()


def test_plugin_routes_protected_under_token_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    aiui = pytest.importorskip("praisonaiui")
    from starlette.testclient import TestClient
    from praisonaiui import server as aiui_server
    from praisonaiui.server import create_app
    from praisonai_code.ship.ui_plugin import plugin

    aiui_server.reset_state()
    monkeypatch.setenv("AIUI_DATA_DIR", str(tmp_path / "aiui-data"))
    monkeypatch.setenv("OPENSHIP_LEDGER_PATH", str(tmp_path / "runs.jsonl"))
    monkeypatch.setenv("OPENSHIP_REPO", str(tmp_path))
    monkeypatch.setenv("AIUI_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setenv("AIUI_REQUIRE_TOKEN", "1")
    monkeypatch.setenv("GATEWAY_AUTH_TOKEN", "test-secret-token-xyz")
    monkeypatch.setattr(service, "get_repo_status", lambda repo, run=None: service.RepoStatus(repo=str(repo), branch="main", base="main"))
    monkeypatch.setattr(service, "list_prs", lambda repo, limit=12, run=None: ([], ""))

    try:
        aiui.set_style("app")
        aiui.register_plugin(plugin)
        aiui.only_my_pages()
        with TestClient(create_app()) as client:
            assert client.get("/api/plugins/openship/pages/openship").status_code in (401, 403)
            assert client.get("/api/plugins/openship/pages/openship", headers={"Authorization": "Bearer test-secret-token-xyz"}).status_code == 200
    finally:
        aiui_server.reset_state()
