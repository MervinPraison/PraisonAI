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


def test_parse_since_window():
    from praisonai_bot.gateway.preflight import parse_since_window

    assert parse_since_window("10m") == 600.0
    assert parse_since_window("2h") == 7200.0
    assert parse_since_window("30") == 30.0


def test_parse_inbound_log(tmp_path):
    from praisonai_bot.gateway.preflight import parse_inbound_log
    import time

    log = tmp_path / "bot-stderr.log"
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    log.write_text(f"{now} - slack - INFO - @mention received: run uname -a\n")

    count, last_at, last_text = parse_inbound_log(str(log), since_seconds=3600)
    assert count == 1
    assert last_text == "run uname -a"
    assert last_at is not None


def test_check_duplicates_no_conflict(tmp_path, monkeypatch):
    from praisonai_bot.gateway.preflight import check_duplicates

    cfg = tmp_path / "bot.yaml"
    cfg.write_text("gateway:\n  host: 127.0.0.1\n  port: 8765\n")

    monkeypatch.setattr(
        "praisonai_bot.gateway.preflight._scan_launch_agent",
        lambda label: __import__(
            "praisonai_bot.gateway.preflight", fromlist=["DuplicateService"]
        ).DuplicateService(label=label, installed=False, running=False),
    )
    monkeypatch.setattr(
        "praisonai_bot.gateway.preflight._read_env_file_tokens",
        lambda _path: {},
    )
    monkeypatch.setattr(
        "praisonai_bot.gateway.preflight._read_hermes_platform_state",
        lambda: {},
    )

    result = check_duplicates(str(cfg))
    assert result.ok is True
    assert result.shared_tokens == []


def test_check_inbound_from_log(tmp_path, monkeypatch):
    from praisonai_bot.gateway.preflight import check_inbound
    import time

    cfg = tmp_path / "bot.yaml"
    cfg.write_text("gateway:\n  host: 127.0.0.1\n  port: 59999\n")
    log = tmp_path / "bot-stderr.log"
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    log.write_text(f"{now} - slack - INFO - @mention received: hello\n")

    result = check_inbound(str(cfg), since="1h", log_path=str(log), probe_results={})
    assert result.ok is True
    assert result.proves == "inbound_delivery"
    assert result.mentions_in_window == 1


def test_check_runtime_unreachable(tmp_path):
    from praisonai_bot.gateway.preflight import check_runtime

    cfg = tmp_path / "bot.yaml"
    cfg.write_text("gateway:\n  host: 127.0.0.1\n  port: 59998\n")
    result = check_runtime(str(cfg), timeout=1.0)
    assert result.ok is False
    assert result.info.ok is False


def test_list_and_show_gateway_sessions(tmp_path, monkeypatch):
    import json

    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    data = {
        "session_id": "bot_slack_U123",
        "user_id": "U123",
        "agent_name": "assistant",
        "messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
        "updated_at": 1_700_000_000,
    }
    (sessions_dir / "bot_slack_U123.json").write_text(json.dumps(data))

    monkeypatch.setattr(
        "praisonai_bot.gateway.preflight._sessions_dir",
        lambda: str(sessions_dir),
    )
    from praisonai_bot.gateway.preflight import list_gateway_sessions, show_gateway_session

    rows = list_gateway_sessions(platform="slack")
    assert len(rows) == 1
    assert rows[0]["session_id"] == "bot_slack_U123"

    shown = show_gateway_session("U123", tail=5)
    assert shown["message_count"] == 2
    assert "footer" in shown
    assert "--check-inbound" in shown["footer"]


def test_resolve_platform_dlq_path():
    from praisonai_bot.gateway.preflight import resolve_platform_dlq_path

    path = resolve_platform_dlq_path("slack")
    assert path.endswith("inbound_dlq.sqlite")
    assert "slack" in path


def test_parse_inbound_log_missing_file(tmp_path):
    from praisonai_bot.gateway.preflight import parse_inbound_log

    count, last_at, last_text = parse_inbound_log(str(tmp_path / "missing.log"), 600)
    assert count == 0
    assert last_at is None
    assert last_text is None


def test_metrics_inbound_delta(tmp_path, monkeypatch):
    import json
    import time

    from praisonai_bot.gateway.preflight import (
        _metrics_baseline_path,
        _metrics_inbound_delta,
        check_inbound,
    )

    baseline = _metrics_baseline_path()
    monkeypatch.setattr(
        "praisonai_bot.gateway.preflight._metrics_baseline_path",
        lambda: str(tmp_path / "baseline.json"),
    )
    monkeypatch.setattr(
        "praisonai_bot.gateway.preflight._scrape_metrics_counter",
        lambda *a, **k: 5.0,
    )

    host, port = "127.0.0.1", 8765
    (tmp_path / "baseline.json").write_text(
        json.dumps({"host": host, "port": port, "counter": 2.0, "ts": time.time()})
    )
    current, delta = _metrics_inbound_delta(host, port, since_seconds=600)
    assert current == 5.0
    assert delta == 3.0

    cfg = tmp_path / "bot.yaml"
    cfg.write_text("gateway:\n  host: 127.0.0.1\n  port: 8765\n")
    log = tmp_path / "bot-stderr.log"
    log.write_text("")
    # Reset baseline so check_inbound sees a fresh delta on the next scrape.
    (tmp_path / "baseline.json").write_text(
        json.dumps({"host": host, "port": port, "counter": 1.0, "ts": time.time()})
    )
    result = check_inbound(str(cfg), since="1h", log_path=str(log))
    assert result.metrics_inbound_delta == 4.0
    assert result.ok is True


def test_check_runtime_success(monkeypatch, tmp_path):
    from praisonai_bot.gateway.preflight import RuntimeProbeResult, check_runtime

    def fake_get(host, port, path, timeout=5.0, auth=False):
        if path == "/info":
            body = {"name": "PraisonAI Gateway", "version": "1.0.0"}
        elif path == "/ready":
            body = {"ready": True}
        elif path == "/live":
            body = {"alive": True}
        else:
            body = {"status": "healthy", "channels": {}}
        return RuntimeProbeResult(ok=True, status_code=200, body=body)

    monkeypatch.setattr("praisonai_bot.gateway.preflight._http_get_json", fake_get)
    cfg = tmp_path / "bot.yaml"
    cfg.write_text("gateway:\n  host: 127.0.0.1\n  port: 8765\n")

    result = check_runtime(str(cfg))
    assert result.ok is True
    assert result.health.ok is True


def test_check_duplicates_shared_token(tmp_path, monkeypatch):
    from praisonai_bot.gateway.preflight import DuplicateService, check_duplicates

    cfg = tmp_path / "bot.yaml"
    cfg.write_text("gateway:\n  host: 127.0.0.1\n  port: 8765\n")

    shared_fp = "abc123shared"

    monkeypatch.setattr(
        "praisonai_bot.gateway.preflight._scan_launch_agent",
        lambda label: DuplicateService(label=label, installed=True, running=False),
    )
    monkeypatch.setattr(
        "praisonai_bot.gateway.preflight._read_env_file_tokens",
        lambda path: {"SLACK_APP_TOKEN": shared_fp}
        if "praisonai" in path
        else {"SLACK_APP_TOKEN": shared_fp},
    )
    monkeypatch.setattr(
        "praisonai_bot.gateway.preflight._read_hermes_platform_state",
        lambda: {},
    )
    monkeypatch.setattr(
        "praisonai_bot.gateway.preflight._token_fingerprint",
        lambda _v: shared_fp,
    )

    result = check_duplicates(str(cfg))
    assert result.shared_tokens == [shared_fp]
    assert result.ok is False
