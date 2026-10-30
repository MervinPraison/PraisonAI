"""Gateway outbound lifecycle sinks (#6140): ``gateway.hooks_outbound``."""

from __future__ import annotations

import asyncio
import json
import sys

import pytest

pytest.importorskip("praisonai_bot.gateway.server")

from praisonaiagents.hooks import HookRunner, get_default_registry  # noqa: E402
from praisonaiagents.hooks.events import SessionEndInput  # noqa: E402
from praisonaiagents.hooks.types import HookEvent  # noqa: E402

from praisonai_bot.bots._config_schema import GatewayServerSchema  # noqa: E402
from praisonai_bot.gateway.server import WebSocketGateway  # noqa: E402


def _bare_server():
    srv = object.__new__(WebSocketGateway)
    srv._hooks = {}
    srv._hook_idem = None
    srv._hook_idempotency_backend = None
    srv._outbound_hook_ids = []
    return srv


@pytest.fixture
def srv(monkeypatch):
    monkeypatch.delenv("PRAISONAI_NO_PLUGINS", raising=False)
    server = _bare_server()
    yield server
    server._apply_outbound_hooks_from_config({})  # leave the global registry clean


def _cfg(*entries):
    return {"gateway": {"hooks_outbound": list(entries)}}


def test_registers_command_hook_and_pipes_event_json(srv, tmp_path):
    out = tmp_path / "event.json"
    cmd = f'{sys.executable} -c "import sys; open(r\'{out}\', \'w\').write(sys.stdin.read())"'
    srv._apply_hooks_from_config(_cfg({"command": cmd, "events": ["session_end"]}))
    assert len(srv._outbound_hook_ids) == 1

    runner = HookRunner(registry=get_default_registry())
    event = SessionEndInput(
        session_id="s1", cwd=".", event_name=HookEvent.SESSION_END,
        timestamp="0", agent_name="bot",
    )
    asyncio.run(runner.execute(HookEvent.SESSION_END, event))
    payload = json.loads(out.read_text())
    assert payload["session_id"] == "s1"


def test_reload_replaces_and_removal_clears(srv):
    registry = get_default_registry()
    srv._apply_hooks_from_config(_cfg({"command": "true", "events": ["gateway_stop", "job_completed"]}))
    srv._apply_hooks_from_config(_cfg({"command": "true", "events": ["gateway_stop"]}))
    assert len(srv._outbound_hook_ids) == 1
    srv._apply_hooks_from_config({})
    assert srv._outbound_hook_ids == []
    assert not any(
        (h.name or "").startswith("outbound:") for h in registry.get_hooks(HookEvent.GATEWAY_STOP)
    )


def test_invalid_entry_skipped(srv):
    srv._apply_hooks_from_config(_cfg({"command": "true", "events": ["nope"]}))
    assert srv._outbound_hook_ids == []


def test_safe_mode_skips(srv, monkeypatch):
    monkeypatch.setenv("PRAISONAI_NO_PLUGINS", "1")
    srv._apply_hooks_from_config(_cfg({"command": "true", "events": ["session_end"]}))
    assert srv._outbound_hook_ids == []


def test_schema_rejects_unknown_event():
    GatewayServerSchema(hooks_outbound=[{"command": "x", "events": ["session_end"]}])
    with pytest.raises(ValueError, match="Unknown hook event"):
        GatewayServerSchema(hooks_outbound=[{"command": "x", "events": ["sesion_end"]}])


def test_stop_fires_gateway_stop_then_unregisters(srv, tmp_path):
    out = tmp_path / "stop.json"
    cmd = f'{sys.executable} -c "import sys; open(r\'{out}\', \'w\').write(sys.stdin.read())"'
    srv._channel_bots = {"telegram": object()}
    srv._apply_hooks_from_config(_cfg({"command": cmd, "events": ["gateway_stop"]}))
    asyncio.run(srv._stop_outbound_hooks())
    payload = json.loads(out.read_text())
    assert payload["platforms"] == ["telegram"] and payload["reason"] == "stop"
    assert srv._outbound_hook_ids == []
    assert not any(
        (h.name or "").startswith("outbound:")
        for h in get_default_registry().get_hooks(HookEvent.GATEWAY_STOP)
    )


def test_channel_botos_exposes_outbound_runner_for_undelivered(srv):
    from praisonai_bot.gateway.server import _ChannelBotOS

    botos = _ChannelBotOS({}, srv._outbound_hook_runner)
    assert botos._get_hook_runner() is None  # no outbound hooks → no runner
    srv._apply_hooks_from_config(_cfg({"command": "true", "events": ["message_undelivered"]}))
    assert isinstance(botos._get_hook_runner(), HookRunner)
    assert _ChannelBotOS({})._get_hook_runner() is None


def test_stop_hook_bounded_by_shutdown_deadline(srv):
    import time

    srv._apply_hooks_from_config(_cfg({"command": "exec sleep 20","events": ["gateway_stop"]}))
    srv._shutdown_deadline_at = time.monotonic() + 1.5  # ~0.5s budget for the hook
    start = time.monotonic()
    asyncio.run(srv._stop_outbound_hooks())
    assert time.monotonic() - start < 5
    assert srv._outbound_hook_ids == []

