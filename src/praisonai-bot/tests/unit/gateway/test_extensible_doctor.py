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

    monkeypatch.setattr(health_registry, "_default_registry", None)
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


def test_gateway_doctor_json_stays_pure_when_registry_warns(monkeypatch, tmp_path):
    """Registry warnings (e.g. plugin discovery) must not corrupt --json output.

    Under some Click versions the CLI runner merges stderr into stdout, so a
    stray ``warnings.warn`` during health-check discovery would break
    ``json.loads`` (the CI JSONDecodeError). The doctor must keep stdout as a
    single valid JSON document regardless.
    """
    import warnings as _warnings

    typer_testing = pytest.importorskip("typer.testing")
    from praisonaiagents.gateway.config import GATEWAY_CONFIG_VERSION
    import praisonaiagents.runtime.health_registry as health_registry

    monkeypatch.setattr(health_registry, "_default_registry", None)

    def _noisy_discovery(self):
        _warnings.warn("Failed to load health check 'demo': boom")

    monkeypatch.setattr(
        health_registry.HealthCheckRegistry,
        "_load_entry_points",
        _noisy_discovery,
    )

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
