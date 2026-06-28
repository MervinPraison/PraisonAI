"""Tests for gateway pre-flight channel credential validation (#2426).

Covers:
- ``BotOS.probe_all()`` aggregate
- CLI helpers ``_probe_channels`` / ``_render_probe_results`` / ``_resolve_env_token``
- ``gateway doctor`` and ``gateway channels --probe`` exit codes
"""

import asyncio

import pytest

from praisonai.bots import Bot, BotOS
from praisonaiagents.bots import ProbeResult


def _patch_probe(monkeypatch):
    async def fake_probe(self):
        if self._platform == "slack":
            return ProbeResult(ok=False, platform="slack", error="invalid_auth")
        return ProbeResult(ok=True, platform=self._platform, bot_username="support_bot")

    monkeypatch.setattr(Bot, "probe", fake_probe)


def test_probe_all_aggregates_results(monkeypatch):
    _patch_probe(monkeypatch)
    botos = BotOS(
        bots=[Bot("telegram", token="x"), Bot("slack", token="y")],
        enable_supervision=False,
    )
    res = asyncio.run(botos.probe_all())
    assert set(res) == {"telegram", "slack"}
    assert res["telegram"].ok is True
    assert res["telegram"].bot_username == "support_bot"
    assert res["slack"].ok is False
    assert "invalid_auth" in res["slack"].error


def test_probe_all_empty():
    botos = BotOS(bots=[], enable_supervision=False)
    assert asyncio.run(botos.probe_all()) == {}


def test_resolve_env_token(monkeypatch):
    from praisonai.cli.commands.gateway import _resolve_env_token

    monkeypatch.setenv("MY_TOKEN", "abc123")
    assert _resolve_env_token("${MY_TOKEN}") == "abc123"
    assert _resolve_env_token("literal") == "literal"
    assert _resolve_env_token("${MISSING_TOKEN}") == ""


def test_probe_channels_and_render(monkeypatch, capsys):
    _patch_probe(monkeypatch)
    from praisonai.cli.commands.gateway import _probe_channels, _render_probe_results

    channels = {
        "telegram": {"platform": "telegram", "token": "t"},
        "slack": {"platform": "slack", "token": "s"},
    }
    results = asyncio.run(_probe_channels(channels))
    all_ok = _render_probe_results(results)
    out = capsys.readouterr().out
    assert all_ok is False
    assert "telegram" in out and "✓" in out
    assert "@support_bot" in out
    assert "slack" in out and "✗" in out and "invalid_auth" in out


def test_doctor_command_exits_nonzero_on_failure(monkeypatch, tmp_path):
    typer_testing = pytest.importorskip("typer.testing")
    _patch_probe(monkeypatch)

    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(
        "channels:\n"
        "  telegram:\n    platform: telegram\n    token: t\n"
        "  slack:\n    platform: slack\n    token: s\n"
    )

    from praisonai.cli.commands.gateway import app

    runner = typer_testing.CliRunner()
    result = runner.invoke(app, ["doctor", "--config", str(cfg)])
    assert result.exit_code == 1
    assert "telegram" in result.stdout
    assert "slack" in result.stdout


def test_channels_probe_flag_passes_when_all_ok(monkeypatch, tmp_path):
    typer_testing = pytest.importorskip("typer.testing")

    async def all_ok_probe(self):
        return ProbeResult(ok=True, platform=self._platform, bot_username="bot")

    monkeypatch.setattr(Bot, "probe", all_ok_probe)

    cfg = tmp_path / "gateway.yaml"
    cfg.write_text("channels:\n  telegram:\n    platform: telegram\n    token: t\n")

    from praisonai.cli.commands.gateway import app

    runner = typer_testing.CliRunner()
    result = runner.invoke(app, ["channels", "--probe", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "telegram" in result.stdout


def test_start_preflight_fails_fast_on_bad_token(monkeypatch, tmp_path):
    typer_testing = pytest.importorskip("typer.testing")
    _patch_probe(monkeypatch)

    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(
        "channels:\n"
        "  slack:\n    platform: slack\n    token: s\n"
    )

    import praisonai.cli.features.gateway as gw_feature

    def _fail_if_called(self, *a, **k):  # pragma: no cover - must not run
        raise AssertionError("handler.start() must not run on preflight failure")

    monkeypatch.setattr(gw_feature.GatewayHandler, "start", _fail_if_called)

    from praisonai.cli.commands.gateway import app

    runner = typer_testing.CliRunner()
    result = runner.invoke(app, ["start", "--config", str(cfg)])
    assert result.exit_code == 1
    assert "slack" in result.stdout


def test_start_no_preflight_skips_probe(monkeypatch, tmp_path):
    typer_testing = pytest.importorskip("typer.testing")

    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(
        "channels:\n"
        "  slack:\n    platform: slack\n    token: s\n"
    )

    async def _must_not_probe(self):  # pragma: no cover - must not run
        raise AssertionError("probe must not run with --no-preflight")

    monkeypatch.setattr(Bot, "probe", _must_not_probe)

    import praisonai.cli.features.gateway as gw_feature

    started = {}

    def _record_start(self, *a, **k):
        started["called"] = True

    monkeypatch.setattr(gw_feature.GatewayHandler, "start", _record_start)

    from praisonai.cli.commands.gateway import app

    runner = typer_testing.CliRunner()
    result = runner.invoke(app, ["start", "--config", str(cfg), "--no-preflight"])
    assert result.exit_code == 0
    assert started.get("called") is True
