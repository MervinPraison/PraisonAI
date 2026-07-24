"""Tests for praisonai_bot.gateway.preflight helpers."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from praisonaiagents.bots import ProbeResult


def test_run_shell_readiness_no_shell_channels(tmp_path):
    cfg = tmp_path / "bot.yaml"
    cfg.write_text(
        "channels:\n"
        "  slack:\n    platform: slack\n    token: x\n"
        "agents:\n  assistant:\n    instructions: hi\n"
    )
    from praisonai_bot.gateway.preflight import run_shell_readiness_check

    result = run_shell_readiness_check(str(cfg))
    assert result.ok is True
    assert "No channels with allow_shell" in result.message


def test_run_shell_readiness_wires_execute_command(tmp_path):
    cfg = tmp_path / "bot.yaml"
    cfg.write_text(
        "channels:\n"
        "  slack:\n"
        "    platform: slack\n"
        "    token: x\n"
        "    allow_shell: true\n"
        "    auto_approve_shell: true\n"
        "agents:\n"
        "  assistant:\n"
        "    name: assistant\n"
        "    instructions: hi\n"
        "routing:\n  default: assistant\n"
    )
    from praisonai_bot.gateway.preflight import run_shell_readiness_check

    result = run_shell_readiness_check(str(cfg))
    assert result.ok is True
    assert result.issues == []


def test_probe_channels_from_config_filters_channel(tmp_path, monkeypatch):
    cfg = tmp_path / "bot.yaml"
    cfg.write_text(
        "channels:\n"
        "  telegram:\n    platform: telegram\n    token: t\n"
        "  slack:\n    platform: slack\n    token: s\n"
    )

    async def fake_probe(channels, timeout=15.0):
        return {name: ProbeResult(ok=True, platform=name, bot_username="bot") for name in channels}

    monkeypatch.setattr(
        "praisonai_bot.gateway.preflight.probe_channels",
        fake_probe,
    )
    from praisonai_bot.gateway.preflight import probe_channels_from_config

    results = asyncio.run(probe_channels_from_config(str(cfg), channel_filter="slack"))
    assert set(results) == {"slack"}


def test_check_gateway_running_unreachable(tmp_path):
    cfg = tmp_path / "bot.yaml"
    cfg.write_text("gateway:\n  host: 127.0.0.1\n  port: 59999\n")
    from praisonai_bot.gateway.preflight import check_gateway_running

    ok, msg = check_gateway_running(str(cfg), timeout=1.0)
    assert ok is False
    assert "59999" in msg


def test_run_turn_test_mocked(tmp_path, monkeypatch):
    cfg = tmp_path / "bot.yaml"
    cfg.write_text(
        "channels:\n"
        "  slack:\n"
        "    platform: slack\n"
        "    token: x\n"
        "agents:\n"
        "  assistant:\n"
        "    name: assistant\n"
        "    instructions: hi\n"
        "routing:\n  default: assistant\n"
    )

    mock_chat = AsyncMock(return_value="OK from test")
    monkeypatch.setattr(
        "praisonai_bot.bots._session.BotSessionManager.chat",
        mock_chat,
    )
    from praisonai_bot.gateway.preflight import run_turn_test

    ok, message = asyncio.run(run_turn_test(str(cfg), "slack", "Say OK"))
    assert ok is True
    assert message == "OK from test"
