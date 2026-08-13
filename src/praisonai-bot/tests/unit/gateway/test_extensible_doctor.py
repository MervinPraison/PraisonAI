"""Integration coverage for plugin-contributed gateway health checks."""

import json

import pytest


def test_gateway_doctor_runs_repairs_and_revalidates_registered_check(
    monkeypatch, tmp_path
):
    typer_testing = pytest.importorskip("typer.testing")
    from praisonaiagents.gateway.config import GATEWAY_CONFIG_VERSION
    from praisonaiagents.runtime.doctor_protocol import Finding
    from praisonaiagents.runtime.health_check import HealthRepairResult
    import praisonaiagents.runtime.health_registry as health_registry

    class PluginCheck:
        check_id = "channel/example/webhook"

        def __init__(self):
            self.healthy = False

        def detect(self, context):
            if self.healthy:
                return []
            return [Finding(
                rule_id=self.check_id,
                severity="error",
                message="webhook is unreachable",
                fix_description="re-register the webhook",
            )]

        def repair(self, context, findings):
            self.healthy = True
            return HealthRepairResult(changed=True, message="webhook registered")

    monkeypatch.setattr(
        health_registry,
        "_default_registry",
        health_registry.HealthCheckRegistry(discover_plugins=False),
    )
    monkeypatch.delenv("GATEWAY_AUTH_TOKEN", raising=False)
    health_registry.register_health_check(PluginCheck())

    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(
        f"config_version: {GATEWAY_CONFIG_VERSION}\nchannels: {{}}\n",
        encoding="utf-8",
    )

    from praisonai_bot.cli.commands.gateway import app

    result = typer_testing.CliRunner().invoke(
        app, ["doctor", "--config", str(cfg), "--fix", "--json"]
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["health"]["checksRun"] == 3
    assert payload["health"]["repaired"] == 1
    assert payload["health"]["validated"] == 3
    plugin = next(
        item for item in payload["health"]["results"]
        if item["id"] == "channel/example/webhook"
    )
    assert plugin["repaired"] is True
    assert plugin["residual_findings"] == []


def test_gateway_doctor_json_stays_pure_when_auth_token_env_is_weak(
    monkeypatch, tmp_path
):
    """`doctor --json` stdout must be a single JSON document even when the
    ambient GATEWAY_AUTH_TOKEN is a known-weak placeholder (the advisory is
    routed to stderr). Guards the CI JSONDecodeError regression."""
    typer_testing = pytest.importorskip("typer.testing")
    from praisonaiagents.gateway.config import GATEWAY_CONFIG_VERSION
    import praisonaiagents.runtime.health_registry as health_registry

    monkeypatch.setattr(
        health_registry,
        "_default_registry",
        health_registry.HealthCheckRegistry(discover_plugins=False),
    )
    monkeypatch.setenv("GATEWAY_AUTH_TOKEN", "changeme")

    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(
        f"config_version: {GATEWAY_CONFIG_VERSION}\nchannels: {{}}\n",
        encoding="utf-8",
    )

    from praisonai_bot.cli.commands.gateway import app

    result = typer_testing.CliRunner().invoke(
        app, ["doctor", "--config", str(cfg), "--json"]
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["health"]["checksRun"] == 2
    assert "known-weak" in result.stderr


def test_gateway_doctor_dry_run_previews_plugin_repair(monkeypatch, tmp_path):
    typer_testing = pytest.importorskip("typer.testing")
    from praisonaiagents.gateway.config import GATEWAY_CONFIG_VERSION
    from praisonaiagents.runtime.doctor_protocol import Finding
    from praisonaiagents.runtime.health_check import HealthRepairResult
    import praisonaiagents.runtime.health_registry as health_registry

    class PreviewCheck:
        check_id = "channel/example/preview"

        def __init__(self):
            self.changed = False

        def detect(self, context):
            if self.changed:
                return []
            return [Finding(
                rule_id=self.check_id,
                severity="warning",
                message="preview needed",
            )]

        def repair(self, context, findings):
            if context.get("dry_run"):
                return HealthRepairResult(
                    changed=False, message="plugin: would repair (--dry-run)"
                )
            self.changed = True
            return HealthRepairResult(changed=True, message="plugin repaired")

    check = PreviewCheck()
    monkeypatch.setattr(
        health_registry,
        "_default_registry",
        health_registry.HealthCheckRegistry(discover_plugins=False),
    )
    monkeypatch.setenv("GATEWAY_AUTH_TOKEN", "a" * 32)
    health_registry.register_health_check(check)
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(
        f"config_version: {GATEWAY_CONFIG_VERSION}\nchannels: {{}}\n",
        encoding="utf-8",
    )

    from praisonai_bot.cli.commands.gateway import app

    result = typer_testing.CliRunner().invoke(
        app, ["doctor", "--config", str(cfg), "--fix", "--dry-run", "--json"]
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    plugin = next(
        item for item in payload["health"]["results"]
        if item["id"] == check.check_id
    )
    assert payload["health"]["repaired"] == 0
    assert plugin["repair"]["message"] == "plugin: would repair (--dry-run)"
    assert check.changed is False


def test_gateway_doctor_fails_for_diagnostic_only_error(monkeypatch, tmp_path):
    typer_testing = pytest.importorskip("typer.testing")
    from praisonaiagents.gateway.config import GATEWAY_CONFIG_VERSION
    from praisonaiagents.runtime.doctor_protocol import Finding
    import praisonaiagents.runtime.health_registry as health_registry

    class DiagnosticOnly:
        check_id = "channel/example/diagnostic"

        def detect(self, context):
            return [Finding(
                rule_id=self.check_id,
                severity="error",
                message="manual remediation required",
            )]

    monkeypatch.setattr(
        health_registry,
        "_default_registry",
        health_registry.HealthCheckRegistry(discover_plugins=False),
    )
    monkeypatch.setenv("GATEWAY_AUTH_TOKEN", "a" * 32)
    health_registry.register_health_check(DiagnosticOnly())
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(
        f"config_version: {GATEWAY_CONFIG_VERSION}\nchannels: {{}}\n",
        encoding="utf-8",
    )

    from praisonai_bot.cli.commands.gateway import app

    result = typer_testing.CliRunner().invoke(
        app, ["doctor", "--config", str(cfg), "--json"]
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    diagnostic = next(
        item for item in payload["health"]["results"]
        if item["id"] == DiagnosticOnly.check_id
    )
    assert diagnostic["residual_findings"][0]["severity"] == "error"
