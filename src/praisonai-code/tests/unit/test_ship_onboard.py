"""Unit tests for OpenShip zero-friction onboarding (`ship init`, `ship check`, `ship ui`)."""

from __future__ import annotations

import importlib.util
import subprocess
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

    # Generated YAML must be valid and use the praisonai-code CLI binary
    wf = yaml.safe_load((tmp_path / ".github" / "workflows" / "openship.yml").read_text(encoding="utf-8"))
    assert {"review", "steward", "approvals"}.issubset(wf["jobs"].keys())
    wf_raw = (tmp_path / ".github" / "workflows" / "openship.yml").read_text(encoding="utf-8")
    assert "praisonai-code ship" in wf_raw
    assert "praisonai-code steward" in wf_raw
    assert "praisonai-code approvals" in wf_raw

    # Never echo secret values in formatted output
    formatted = onboard.format_init_result(res1)
    assert "sk-test-secret-do-not-print" not in formatted
    assert "OPENAI_API_KEY" in formatted

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


def test_init_repo_refuses_outside_git_repo(tmp_path: Path) -> None:
    def _no_git(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="not a git repo")

    with pytest.raises(ShipRefused, match="not inside a git repository"):
        onboard.init_repo(tmp_path, run=_no_git)


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


def test_cli_ship_check_and_init_and_ui(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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
    import praisonai_code.ship.ui_plugin as ui_plugin

    called = {}
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(
        ui_plugin,
        "serve_openship",
        lambda **kw: called.update(kw),
    )
    res_ui_ok = runner.invoke(ship_cmd.app, ["ui"])
    assert res_ui_ok.exit_code == 0
    assert called["host"] == "127.0.0.1"
    assert called["port"] == 8765
