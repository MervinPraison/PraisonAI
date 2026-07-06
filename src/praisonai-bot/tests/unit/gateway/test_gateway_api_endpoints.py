#!/usr/bin/env python3
"""Tests for the gateway's additive OpenAI-compatible / MCP protocol surfaces.

These verify that the config-gated ``/v1/*`` and ``/mcp`` handlers dispatch into
the gateway's own registered agents and reuse its session store, without a
second process or copy of agent state (Issue #2715).
"""

import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai"))
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai-agents"))

from praisonaiagents.gateway import GatewayConfig, ApiConfig
from praisonai_bot.gateway.api_endpoints import GatewayApiEndpoints, _extract_text


class _FakeAgent:
    async def achat(self, content):
        return f"echo:{content}"


class _FakeSession:
    session_id = "sid-1"


class _FakeGateway:
    """Minimal gateway-shaped object exercising the adapter's public calls."""

    def __init__(self):
        self._agent = _FakeAgent()
        self._admission_gate = None
        self.created_sessions = []

    def list_agents(self):
        return ["assistant"]

    def get_agent(self, aid):
        return self._agent if aid == "assistant" else None

    def create_session(self, agent_id, session_id=None):
        self.created_sessions.append((agent_id, session_id))
        return _FakeSession()

    @staticmethod
    async def _dispatch_agent_turn(agent, content):
        return await agent.achat(content)


class _FakeReq:
    def __init__(self, body, headers=None):
        self._body = body
        self.headers = headers or {}

    async def json(self):
        return self._body


def _body(resp):
    return json.loads(resp.body.decode())


def test_extract_text_prefers_last_user_and_prepends_system():
    text = _extract_text(
        [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "first"},
            {"role": "user", "content": "second"},
        ]
    )
    assert "be brief" in text
    assert text.endswith("second")


def test_openai_chat_dispatches_to_registered_agent():
    ep = GatewayApiEndpoints(_FakeGateway())
    resp = asyncio.run(
        ep.openai_chat(
            _FakeReq(
                {"model": "assistant", "messages": [{"role": "user", "content": "hi"}]}
            )
        )
    )
    data = _body(resp)
    assert data["object"] == "chat.completion"
    assert data["choices"][0]["message"]["content"] == "echo:hi"


def test_openai_chat_no_agents_returns_503():
    class _Empty(_FakeGateway):
        def list_agents(self):
            return []

    ep = GatewayApiEndpoints(_Empty())
    resp = asyncio.run(
        ep.openai_chat(_FakeReq({"messages": [{"role": "user", "content": "hi"}]}))
    )
    assert resp.status_code == 503


def test_openai_models_lists_registered_agents():
    ep = GatewayApiEndpoints(_FakeGateway())
    resp = asyncio.run(ep.openai_models(_FakeReq({})))
    data = _body(resp)
    assert data["data"][0]["id"] == "assistant"


def test_openai_responses_dispatches():
    ep = GatewayApiEndpoints(_FakeGateway())
    resp = asyncio.run(
        ep.openai_responses(_FakeReq({"model": "assistant", "input": "ping"}))
    )
    data = _body(resp)
    assert data["output_text"] == "echo:ping"


def test_mcp_initialize_and_tools_list():
    ep = GatewayApiEndpoints(_FakeGateway())
    init = asyncio.run(
        ep.mcp_jsonrpc(_FakeReq({"jsonrpc": "2.0", "id": 1, "method": "initialize"}))
    )
    assert _body(init)["result"]["serverInfo"]["name"] == "PraisonAI Gateway"

    listed = asyncio.run(
        ep.mcp_jsonrpc(_FakeReq({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))
    )
    tools = _body(listed)["result"]["tools"]
    assert tools[0]["name"] == "assistant"


def test_mcp_tools_call_dispatches():
    ep = GatewayApiEndpoints(_FakeGateway())
    resp = asyncio.run(
        ep.mcp_jsonrpc(
            _FakeReq(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "assistant", "arguments": {"message": "yo"}},
                }
            )
        )
    )
    result = _body(resp)["result"]
    assert result["content"][0]["text"] == "echo:yo"
    assert result["isError"] is False


def test_mcp_unknown_method_returns_error():
    ep = GatewayApiEndpoints(_FakeGateway())
    resp = asyncio.run(
        ep.mcp_jsonrpc(_FakeReq({"jsonrpc": "2.0", "id": 4, "method": "bogus"}))
    )
    assert _body(resp)["error"]["code"] == -32601


def test_session_reused_per_caller_key():
    gw = _FakeGateway()
    ep = GatewayApiEndpoints(gw)
    req = _FakeReq(
        {"model": "assistant", "messages": [{"role": "user", "content": "x"}]},
        headers={"x-session-id": "conv-42"},
    )
    asyncio.run(ep.openai_chat(req))
    asyncio.run(ep.openai_chat(req))
    # Both turns pin the same stable session id derived from the header.
    assert gw.created_sessions[0][1] == gw.created_sessions[1][1]
    assert "conv-42" in gw.created_sessions[0][1]


def test_construct_gateway_with_api_flags():
    from praisonai_bot.gateway.server import WebSocketGateway

    gw = WebSocketGateway(config=GatewayConfig(), openai_api=True, mcp=True)
    assert gw.config.api.openai is True
    assert gw.config.api.mcp is True
    assert gw.config.api.enabled is True


def test_api_config_disabled_by_default():
    assert ApiConfig().enabled is False
    assert GatewayConfig().api.enabled is False
