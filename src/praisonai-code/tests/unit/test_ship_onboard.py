"""Unit tests for OpenShip zero-friction onboarding (`ship init`, `ship check`, `ship ui`)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import types
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from praisonai_code.cli.commands import ship as ship_cmd
from praisonai_code.ship import onboard
from praisonai_code.ship.flow import ShipRefused


def _fake_git_run(repo: Path, *, branch: str = "feat/demo", gh_ok: bool = True):
    def _run(cmd, **kwargs):
        if cmd[:3] == ["git", "rev-parse", "--show-toplevel"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=f"{repo}\n", stderr="")
        if cmd[:3] == ["git", "rev-parse", "--abbrev-ref"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=f"{branch}\n", stderr="")
        if cmd[:3] == ["gh", "auth", "status"]:
            return subprocess.CompletedProcess(cmd, 0 if gh_ok else 1, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="unexpected command")

    return _run


def test_init_repo_creates_all_three_files_and_is_idempotent(tmp_path: Path) -> None:
    run = _fake_git_run(tmp_path)
    res1 = onboard.init_repo(
        tmp_path,
        run=run,
        env={"OPENAI_API_KEY": "sk-test-secret-do-not-print"},
        which=lambda name: f"/usr/bin/{name}" if name == "gh" else None,
        find_spec=lambda name: object() if name == "praisonaiui" else None,
    )
    assert res1.created == [
        ".github/workflows/openship.yml",
        ".praisonai/approvals.yml",
        "REVIEW.md",
    ]
    assert res1.kept == []
    assert (tmp_path / ".github" / "workflows" / "openship.yml").is_file()
    assert (tmp_path / ".praisonai" / "approvals.yml").is_file()
    assert (tmp_path / "REVIEW.md").is_file()

    # Generated YAML must be valid, use praisonai-code CLI, set GH_REPO before checkout,
    # and re-evaluate approvals on workflow_run completion.
    wf_raw = (tmp_path / ".github" / "workflows" / "openship.yml").read_text(encoding="utf-8")
    wf = yaml.safe_load(wf_raw)
    assert {"review", "steward", "approvals"}.issubset(wf["jobs"].keys())
    assert "praisonai-code ship" in wf_raw
    assert "praisonai-code steward" in wf_raw
    assert "praisonai-code approvals" in wf_raw
    assert "GH_REPO: ${{ github.repository }}" in wf_raw
    assert "workflow_run" in wf["jobs"]["approvals"]["if"]

    # Never echo secret values; use git -C <repo_root> so subdirectory invocations work
    formatted = onboard.format_init_result(res1)
    assert "sk-test-secret-do-not-print" not in formatted
    assert "OPENAI_API_KEY" in formatted
    assert f"git -C {tmp_path}" in formatted or f"git -C '{tmp_path}'" in formatted

    # Re-running preserves user edits
    custom = "# my custom review rules\n"
    (tmp_path / "REVIEW.md").write_text(custom, encoding="utf-8")
    res2 = onboard.init_repo(
        tmp_path,
        run=run,
        env={},
        which=lambda _: None,
        find_spec=lambda _: None,
    )
    assert res2.created == []
    assert set(res2.kept) == {
        ".github/workflows/openship.yml",
        ".praisonai/approvals.yml",
        "REVIEW.md",
    }
    assert (tmp_path / "REVIEW.md").read_text(encoding="utf-8") == custom


def test_init_repo_matches_default_model_to_configured_provider_key(tmp_path: Path) -> None:
    res = onboard.init_repo(
        tmp_path,
        run=_fake_git_run(tmp_path),
        env={"ANTHROPIC_API_KEY": "sk-ant-test"},
        which=lambda name: f"/usr/bin/{name}" if name == "gh" else None,
        find_spec=lambda _: None,
    )
    assert res.model == "claude-sonnet-4-6"
    wf_raw = (tmp_path / ".github" / "workflows" / "openship.yml").read_text(encoding="utf-8")
    assert "vars.OPENSHIP_MODEL || 'claude-sonnet-4-6'" in wf_raw
    out = onboard.format_init_result(res)
    assert "sk-ant-test" not in out
    assert "ANTHROPIC_API_KEY" in out
    assert "gh variable set OPENSHIP_MODEL --body claude-sonnet-4-6" in out


def test_init_repo_dry_run_writes_nothing(tmp_path: Path) -> None:
    res = onboard.init_repo(
        tmp_path,
        dry_run=True,
        model="claude-sonnet-4-6",
        effort="medium",
        run=_fake_git_run(tmp_path),
        env={},
        which=lambda _: None,
        find_spec=lambda _: None,
    )
    assert res.created == []
    assert res.would_create == [
        ".github/workflows/openship.yml",
        ".praisonai/approvals.yml",
        "REVIEW.md",
    ]
    assert not (tmp_path / ".github").exists()
    assert not (tmp_path / ".praisonai").exists()
    assert not (tmp_path / "REVIEW.md").exists()


def test_init_repo_custom_model_and_validation(tmp_path: Path) -> None:
    res = onboard.init_repo(
        tmp_path,
        model="ollama/qwen3.5:9b",
        effort="low",
        run=_fake_git_run(tmp_path),
        env={},
        which=lambda _: None,
        find_spec=lambda _: None,
    )
    assert ".github/workflows/openship.yml" in res.created
    wf_raw = (tmp_path / ".github" / "workflows" / "openship.yml").read_text(encoding="utf-8")
    assert "vars.OPENSHIP_MODEL || 'ollama/qwen3.5:9b'" in wf_raw
    assert "vars.OPENSHIP_EFFORT || 'low'" in wf_raw

    with pytest.raises(ValueError, match="invalid model"):
        onboard.render_workflow_yaml(model="bad model\ninjection")
    with pytest.raises(ValueError, match="unknown review effort"):
        onboard.render_workflow_yaml(effort="extreme")


def test_init_and_check_handle_missing_git_distinct_from_non_repo(tmp_path: Path) -> None:
    def _no_git_bin(cmd, **kwargs):
        raise FileNotFoundError("git")

    report = onboard.check_readiness(tmp_path, run=_no_git_bin, env={}, which=lambda _: None, find_spec=lambda _: None)
    assert report.git_installed is False
    assert report.repo_root is None
    text = onboard.format_readiness(report)
    assert "missing `git` CLI" in text

    with pytest.raises(ShipRefused, match="not installed"):
        onboard.init_repo(tmp_path, run=_no_git_bin)

    def _not_a_repo(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="not a git repo")

    with pytest.raises(ShipRefused, match="not inside a git repository"):
        onboard.init_repo(tmp_path, run=_not_a_repo)


def test_init_repo_respects_existing_dot_praisonai_review_md(tmp_path: Path) -> None:
    (tmp_path / ".praisonai").mkdir()
    (tmp_path / ".praisonai" / "REVIEW.md").write_text("# nested rules\n", encoding="utf-8")
    res = onboard.init_repo(
        tmp_path,
        run=_fake_git_run(tmp_path),
        env={},
        which=lambda _: None,
        find_spec=lambda _: None,
    )
    assert "REVIEW.md" not in res.created
    assert not (tmp_path / "REVIEW.md").exists()
    assert res.readiness.has_review_md is True


def test_cli_ship_check_init_and_ui_core_only_safe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()

    # ship check
    monkeypatch.setattr(
        onboard,
        "check_readiness",
        lambda: onboard.ReadinessReport(
            repo_root=tmp_path,
            branch="feat/test",
            gh_installed=True,
            gh_authed=True,
            llm_env_vars=["OPENAI_API_KEY"],
            ui_installed=False,
        ),
    )
    res_check = runner.invoke(ship_cmd.app, ["check"])
    assert res_check.exit_code == 0
    assert "OpenShip readiness check:" in res_check.output
    assert 'pip install "praisonai-code[ui]"' in res_check.output

    # ship init --dry-run
    monkeypatch.setattr(
        onboard,
        "init_repo",
        lambda **kw: onboard.InitResult(
            repo_root=tmp_path,
            would_create=[".github/workflows/openship.yml"],
            readiness=onboard.ReadinessReport(repo_root=tmp_path),
        ),
    )
    res_init = runner.invoke(ship_cmd.app, ["init", "--dry-run"])
    assert res_init.exit_code == 0
    assert "would create .github/workflows/openship.yml" in res_init.output

    # ship ui when praisonaiui missing exits cleanly with install hint
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    res_ui_missing = runner.invoke(ship_cmd.app, ["ui"])
    assert res_ui_missing.exit_code == 1
    assert 'pip install "praisonai-code[ui]"' in res_ui_missing.output

    # ship ui when praisonaiui installed delegates to serve_openship on loopback
    # (works even in core-only CI environments without praisonaiui installed)
    called = {}
    fake_plugin = types.ModuleType("praisonai_code.ship.ui_plugin")
    fake_plugin.serve_openship = lambda **kw: called.update(kw)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "praisonai_code.ship.ui_plugin", fake_plugin)
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    res_ui_ok = runner.invoke(ship_cmd.app, ["ui"])
    assert res_ui_ok.exit_code == 0
    assert called["host"] == "127.0.0.1"
    assert called["port"] == 8765


def test_cli_ship_review_parity_dry_run_findings_and_kill_switch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from praisonai_code.ship import ui_service

    runner = CliRunner()
    monkeypatch.setattr(ui_service, "get_repo_root", lambda: tmp_path)

    # 1. --dry-run previews files without calling any LLM
    monkeypatch.setattr(
        ui_service,
        "get_diff_bundle",
        lambda repo, **kw: ("diff --git a/app.py b/app.py\n+x = 1\n", [ui_service.FileDiff("app.py", "", "x = 1")], "working branch"),
    )
    res_dry = runner.invoke(ship_cmd.app, ["review", "--dry-run", "--effort", "low"])
    assert res_dry.exit_code == 0
    assert "Would review 1 file(s) from working branch (effort=low): app.py" in res_dry.output

    # 2. Live findings output (typed severity + path:line + fix)
    monkeypatch.setattr(
        ui_service,
        "run_review",
        lambda repo, **kw: {
            "source": "working branch",
            "severity": "high",
            "diff": "diff --git a/app.py b/app.py\n+KEY='secret'\n",
            "findings": [
                {"severity": "important", "path": "app.py", "line": 4, "title": "Hard-coded key", "fix": "Use env var"}
            ],
        },
    )
    res_found = runner.invoke(ship_cmd.app, ["review", "--model", "ollama/qwen3.5"])
    assert res_found.exit_code == 0
    assert "found 1 issue(s) (severity: high, source: working branch)" in res_found.output
    assert "[important] app.py:4: Hard-coded key — Use env var" in res_found.output

    # 3. Clean diff message
    monkeypatch.setattr(
        ui_service,
        "run_review",
        lambda repo, **kw: {"source": "working branch", "severity": "none", "diff": "", "findings": []},
    )
    res_empty = runner.invoke(ship_cmd.app, ["review"])
    assert res_empty.exit_code == 0
    assert "no local changes to review" in res_empty.output

    # 4. Respects PRAISONAI_DISABLE_SHIP=1 kill switch
    monkeypatch.setenv("PRAISONAI_DISABLE_SHIP", "1")
    res_off = runner.invoke(ship_cmd.app, ["review"])
    assert res_off.exit_code == 1
    assert "disabled" in res_off.output


def test_ui_service_diff_bundle_falls_back_to_branch_diff_and_loads_review_md(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from praisonai_code.ship import review as review_mod
    from praisonai_code.ship import ui_service

    monkeypatch.setenv("OPENSHIP_LEDGER_PATH", str(tmp_path / "ledger.jsonl"))
    (tmp_path / "REVIEW.md").write_text("# Strict security rules\n", encoding="utf-8")

    branch_diff = "diff --git a/src/auth.py b/src/auth.py\n--- a/src/auth.py\n+++ b/src/auth.py\n@@ -1 +1,2 @@\n def f():\n+    return 1\n"

    def fake_run(cmd, **kw):
        if cmd[:3] == ["git", "diff", "HEAD"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:2] == ["git", "ls-files"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:2] == ["git", "symbolic-ref"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="refs/remotes/origin/release/2.x\n", stderr="")
        if cmd[:3] == ["git", "diff", "origin/release/2.x...HEAD"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=branch_diff, stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

    seen = {}

    def fake_review_diff(diff, *, effort="high", llm=None, guidelines=None, **kw):
        seen.update(diff=diff, effort=effort, llm=llm, guidelines=guidelines)
        return []

    # Launch from a different directory containing a competing REVIEW.md;
    # repo's own REVIEW.md must win over process CWD.
    other_cwd = tmp_path / "other_cwd"
    other_cwd.mkdir()
    (other_cwd / "REVIEW.md").write_text("# Wrong repo rules\n", encoding="utf-8")
    monkeypatch.chdir(other_cwd)

    monkeypatch.setattr(review_mod, "review_diff", fake_review_diff)
    res = ui_service.run_review(tmp_path, effort="high", model="gpt-4o-mini", run=fake_run)
    assert res["source"] == "branch vs origin/release/2.x"
    assert "Strict security rules" in (seen["guidelines"] or "")
    assert "Wrong repo rules" not in (seen["guidelines"] or "")
    assert seen["llm"] == "gpt-4o-mini"


def test_ui_service_empty_remote_diff_does_not_fall_back_to_stale_local_base(tmp_path: Path) -> None:
    from praisonai_code.ship import ui_service

    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[:3] == ["git", "diff", "HEAD"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:2] == ["git", "ls-files"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:2] == ["git", "symbolic-ref"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="refs/remotes/origin/main\n", stderr="")
        if cmd[:3] == ["git", "diff", "origin/main...HEAD"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:3] == ["git", "diff", "main...HEAD"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="diff --git a/stale.py b/stale.py\n+old\n", stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

    diff_text, files, _ = ui_service.get_diff_bundle(tmp_path, run=fake_run)
    assert diff_text == ""
    assert files == []
    assert ["git", "diff", "main...HEAD"] not in calls


def test_default_base_branch_resolves_master_and_gh_fallback_without_origin_head() -> None:
    from praisonai_code.ship import ui_service

    def fake_master(cmd, **kw):
        if cmd[:4] == ["git", "rev-parse", "--verify", "--quiet"] and cmd[4] == "origin/master":
            return subprocess.CompletedProcess(cmd, 0, stdout="abc\n", stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

    assert ui_service._default_base_branch(fake_master) == "master"

    def fake_custom_gh(cmd, **kw):
        if cmd[:3] == ["gh", "repo", "view"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="develop\n", stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

    assert ui_service._default_base_branch(fake_custom_gh) == "develop"
