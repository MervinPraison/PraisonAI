"""Doctor checks for gateway shell readiness and channel probes."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from praisonai_code.cli.features.doctor.models import DoctorConfig
from praisonai_code.cli.features.doctor.checks import gateway_checks


def test_shell_readiness_pass(tmp_path, monkeypatch):
    cfg = tmp_path / "bot.yaml"
    cfg.write_text("channels:\n  slack:\n    allow_shell: true\n")

    mock_result = MagicMock(ok=True, message="Shell wiring OK", issues=[])

    def fake_import(name):
        mod = MagicMock()
        mod.run_shell_readiness_check.return_value = mock_result
        return mod

    monkeypatch.setattr(gateway_checks, "skip_if_no_wrapper", lambda *a, **k: None)
    monkeypatch.setattr(gateway_checks, "skip_if_no_bot_package", lambda *a, **k: None)
    monkeypatch.setattr(
        "praisonai_code._bot_bridge.import_bot_module",
        fake_import,
    )

    result = gateway_checks.check_gateway_shell_readiness(
        DoctorConfig(config_file=str(cfg))
    )
    assert result.status.value == "pass"


def test_channel_probe_deep_mock(tmp_path, monkeypatch):
    cfg = tmp_path / "bot.yaml"
    cfg.write_text(
        "channels:\n  telegram:\n    platform: telegram\n    token: t\n"
    )

    from praisonaiagents.bots import ProbeResult

    async def fake_probe(channels, timeout=15.0):
        return {"telegram": ProbeResult(ok=True, platform="telegram", bot_username="bot")}

    mod = MagicMock()
    mod.load_channels_mapping.return_value = {"telegram": {"platform": "telegram", "token": "t"}}
    mod.probe_channels = fake_probe

    monkeypatch.setattr(gateway_checks, "skip_if_no_wrapper", lambda *a, **k: None)
    monkeypatch.setattr(gateway_checks, "skip_if_no_bot_package", lambda *a, **k: None)
    monkeypatch.setattr(
        "praisonai_code._bot_bridge.import_bot_module",
        lambda name: mod,
    )

    result = gateway_checks.check_gateway_channel_probe(
        DoctorConfig(config_file=str(cfg))
    )
    assert result.status.value == "pass"
    assert "telegram" in (result.details or "")
