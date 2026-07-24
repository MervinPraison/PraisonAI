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


def test_duplicate_services_check(tmp_path, monkeypatch):
    cfg = tmp_path / "bot.yaml"
    cfg.write_text("channels:\n  slack:\n    platform: slack\n")

    dup = MagicMock(
        ok=True,
        warnings=[],
        services=[],
    )
    mod = MagicMock()
    mod.check_duplicates.return_value = dup

    monkeypatch.setattr(gateway_checks, "skip_if_no_wrapper", lambda *a, **k: None)
    monkeypatch.setattr(gateway_checks, "skip_if_no_bot_package", lambda *a, **k: None)
    monkeypatch.setattr(
        "praisonai_code._bot_bridge.import_bot_module",
        lambda name: mod,
    )

    result = gateway_checks.check_gateway_duplicate_services(
        DoctorConfig(config_file=str(cfg))
    )
    assert result.status.value == "pass"


def test_no_inbound_recent_warns(tmp_path, monkeypatch):
    cfg = tmp_path / "bot.yaml"
    cfg.write_text("channels:\n  slack:\n    platform: slack\n")

    inbound = MagicMock(
        ok=False,
        mentions_in_window=0,
        hint="No @mention received",
    )
    mod = MagicMock()
    mod.check_inbound.return_value = inbound

    monkeypatch.setattr(gateway_checks, "skip_if_no_wrapper", lambda *a, **k: None)
    monkeypatch.setattr(gateway_checks, "skip_if_no_bot_package", lambda *a, **k: None)
    monkeypatch.setattr(
        "praisonai_code._bot_bridge.import_bot_module",
        lambda name: mod,
    )

    result = gateway_checks.check_gateway_no_inbound_recent(
        DoctorConfig(config_file=str(cfg))
    )
    assert result.status.value == "warn"


def test_no_inbound_recent_pass(tmp_path, monkeypatch):
    cfg = tmp_path / "bot.yaml"
    cfg.write_text("channels:\n  slack:\n    platform: slack\n")

    inbound = MagicMock(ok=True, mentions_in_window=2, last_mention_at="2026-07-24T08:00:00")
    mod = MagicMock()
    mod.check_inbound.return_value = inbound

    monkeypatch.setattr(gateway_checks, "skip_if_no_wrapper", lambda *a, **k: None)
    monkeypatch.setattr(gateway_checks, "skip_if_no_bot_package", lambda *a, **k: None)
    monkeypatch.setattr(
        "praisonai_code._bot_bridge.import_bot_module",
        lambda name: mod,
    )

    result = gateway_checks.check_gateway_no_inbound_recent(
        DoctorConfig(config_file=str(cfg))
    )
    assert result.status.value == "pass"


def test_duplicate_services_warn(tmp_path, monkeypatch):
    cfg = tmp_path / "bot.yaml"
    cfg.write_text("channels:\n  slack:\n    platform: slack\n")

    dup = MagicMock(ok=False, warnings=["Shared token"], services=[])
    mod = MagicMock()
    mod.check_duplicates.return_value = dup

    monkeypatch.setattr(gateway_checks, "skip_if_no_wrapper", lambda *a, **k: None)
    monkeypatch.setattr(gateway_checks, "skip_if_no_bot_package", lambda *a, **k: None)
    monkeypatch.setattr(
        "praisonai_code._bot_bridge.import_bot_module",
        lambda name: mod,
    )

    result = gateway_checks.check_gateway_duplicate_services(
        DoctorConfig(config_file=str(cfg))
    )
    assert result.status.value == "warn"
