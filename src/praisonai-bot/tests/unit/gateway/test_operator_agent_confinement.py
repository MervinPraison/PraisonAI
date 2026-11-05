"""Operator agent confinement on the gateway (Issue #6253).

``auth_scopes`` may carry ``{"scopes": [...], "agents": [...]}`` per token so
an authenticated operator is confined to specific agents; the plain
``token -> [scopes]`` form keeps today's gateway-wide behaviour.
"""

import asyncio

import pytest

from praisonaiagents.gateway import GatewayConfig
from praisonaiagents.gateway.protocols import EventType, GatewayEvent
from praisonai_bot.gateway.server import WebSocketGateway


class _WS:
    def __init__(self):
        self.sent = []

    async def send_json(self, data):
        self.sent.append(data)

    async def close(self, code=None, reason=None):
        pass


POLICY = {
    "tok_support": {"scopes": ["read", "write"], "agents": ["support"]},
    "tok_legacy": ["read", "write"],
}


def test_resolve_agents_contract():
    cfg = GatewayConfig(auth_token="t", auth_scopes=POLICY)
    assert cfg.resolve_scopes("tok_support") == ["read", "write"]
    assert cfg.resolve_agents("tok_support") == ["support"]
    # Plain list form and no-policy are unconfined (backward compatible).
    assert cfg.resolve_agents("tok_legacy") is None
    assert GatewayConfig().resolve_agents("anything") is None
    # Unknown token still holds no scopes.
    assert cfg.resolve_scopes("nope") == []


def test_yaml_both_shapes_parse_agents():
    from praisonaiagents.gateway.config import MultiChannelGatewayConfig

    flat = {"gateway": {"auth_scopes": {
        "tok_support": {"scopes": ["read", "write"], "agents": ["support"]},
        "tok_legacy": ["read"],
    }}}
    gw = MultiChannelGatewayConfig.from_dict(flat).gateway
    assert gw.resolve_agents("tok_support") == ["support"]
    assert gw.resolve_scopes("tok_support") == ["read", "write"]
    assert gw.resolve_agents("tok_legacy") is None

    tokens = {"gateway": {"auth": {"tokens": [
        {"token": "tok_fin", "scopes": ["read"], "agents": ["finance"]},
    ]}}}
    gw = MultiChannelGatewayConfig.from_dict(tokens).gateway
    assert gw.resolve_agents("tok_fin") == ["finance"]
    assert gw.resolve_scopes("tok_fin") == ["read"]


def _gateway_with_client(agents):
    gw = WebSocketGateway(config=GatewayConfig(auth_token="tmp"))
    gw._agents["support"] = object()
    gw._agents["finance"] = object()
    ws = _WS()
    gw._clients["c1"] = ws
    gw._client_scopes["c1"] = ["read", "write"]
    gw._client_agents["c1"] = agents
    return gw, ws


@pytest.mark.parametrize("frame", ["hello", "join"])
def test_confined_operator_cannot_bind_other_agent(frame):
    gw, ws = _gateway_with_client(["support"])
    asyncio.run(gw._handle_client_message("c1", {"type": frame, "agent_id": "finance"}))
    assert "c1" not in gw._client_sessions
    assert "not found" in str(ws.sent[-1]).lower()


@pytest.mark.parametrize("frame", ["hello", "join"])
def test_confined_operator_binds_allowed_agent(frame):
    gw, _ = _gateway_with_client(["support"])
    asyncio.run(gw._handle_client_message("c1", {"type": frame, "agent_id": "support"}))
    assert gw._sessions[gw._client_sessions["c1"]].agent_id == "support"


def test_join_cannot_resume_foreign_agent_session():
    gw, ws = _gateway_with_client(["support"])
    foreign = gw.create_session("finance", client_id="other")
    asyncio.run(gw._handle_client_message(
        "c1",
        {"type": "join", "agent_id": "support", "session_id": foreign.session_id},
    ))
    assert "c1" not in gw._client_sessions
    assert ws.sent[-1]["type"] == "error"


def test_unconfined_operator_reaches_every_agent():
    gw, _ = _gateway_with_client(None)
    asyncio.run(gw._handle_client_message("c1", {"type": "hello", "agent_id": "finance"}))
    assert gw._sessions[gw._client_sessions["c1"]].agent_id == "finance"


def test_broadcast_withholds_other_agents_events():
    gw, ws = _gateway_with_client(["support"])

    async def _run():
        await gw.broadcast(GatewayEvent(type=EventType.MESSAGE, data={}, source="finance"))
        await gw.broadcast(GatewayEvent(type=EventType.MESSAGE, data={}, source="support"))
        await gw.broadcast(GatewayEvent(type=EventType.MESSAGE, data={}, source="system"))

    asyncio.run(_run())
    assert [f.get("source") for f in ws.sent] == ["support", "system"]


def test_misspelled_grant_key_fails_closed():
    # A typo must not silently drop the confinement (it would reach every agent).
    from praisonaiagents.gateway.config import (
        ConfigValidationError, MultiChannelGatewayConfig,
    )
    from praisonai_bot.bots._config_schema import GatewayServerSchema

    bad = {"tok": {"scopes": ["read"], "agnts": ["support"]}}
    with pytest.raises(ConfigValidationError):
        MultiChannelGatewayConfig.from_dict({"gateway": {"auth_scopes": bad}})
    with pytest.raises(Exception):
        GatewayServerSchema(auth_scopes=bad)
    GatewayServerSchema(auth_scopes=POLICY)  # valid shapes still accepted


class _StopStartup(Exception):
    pass


@pytest.mark.parametrize("gw_yaml", [
    {"auth_scopes": {"tok_support": {"scopes": ["read"], "agents": ["support"]}}},
    {"auth": {"tokens": [{"token": "tok_support", "scopes": ["read"], "agents": ["support"]}]}},
])
def test_start_with_config_applies_yaml_policy(gw_yaml, monkeypatch):
    # The YAML startup path must stamp the policy onto self.config, otherwise
    # resolve_agents() returns None and confinement is silently off.
    gw = WebSocketGateway(config=GatewayConfig(auth_token="tmp"))
    cfg = {"gateway": dict(gw_yaml, session={"persist": False})}
    monkeypatch.setattr(gw, "load_gateway_config", lambda path: cfg)
    monkeypatch.setattr(gw, "_session_store_explicit", False, raising=False)

    def _stop(*a, **k):
        raise _StopStartup

    monkeypatch.setattr(gw, "_build_session_store", _stop)
    with pytest.raises(_StopStartup):
        asyncio.run(gw.start_with_config("gateway.yaml"))
    assert gw.config.resolve_agents("tok_support") == ["support"]
    assert gw.config.resolve_scopes("tok_support") == ["read"]


def test_start_with_config_keeps_python_policy_without_yaml_policy(monkeypatch):
    gw = WebSocketGateway(config=GatewayConfig(auth_token="tmp", auth_scopes=POLICY))
    monkeypatch.setattr(gw, "load_gateway_config", lambda path: {"gateway": {"session": {}}})
    monkeypatch.setattr(gw, "_session_store_explicit", False, raising=False)
    monkeypatch.setattr(gw, "_build_session_store", lambda *a, **k: (_ for _ in ()).throw(_StopStartup()))
    with pytest.raises(_StopStartup):
        asyncio.run(gw.start_with_config("gateway.yaml"))
    assert gw.config.auth_scopes == POLICY
