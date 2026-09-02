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


class _FakeMetrics:
    input_tokens = 11
    output_tokens = 7


class _FakeLLM:
    last_token_metrics = _FakeMetrics()


class _FakeAgent:
    def __init__(self):
        self._llm_instance = _FakeLLM()

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
    async def _dispatch_agent_turn(agent, content, on_complete=None):
        result = await agent.achat(content)
        # Mirror the real gateway: snapshot per-turn state in the same context
        # that produced the result, before returning to the caller.
        if on_complete is not None:
            on_complete(agent)
        return result


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


def test_extract_text_preserves_full_history_when_assistant_turns_present():
    # Externally-built history (stateless OpenAI-SDK style) must not be dropped.
    text = _extract_text(
        [
            {"role": "user", "content": "my name is Sam"},
            {"role": "assistant", "content": "Hi Sam!"},
            {"role": "user", "content": "what is my name?"},
        ]
    )
    assert "Sam" in text
    assert "User: my name is Sam" in text
    assert "Assistant: Hi Sam!" in text
    assert text.endswith("what is my name?")


def test_openai_error_body_is_spec_shaped():
    ep = GatewayApiEndpoints(_FakeGateway())

    class _BadReq(_FakeReq):
        async def json(self):
            raise ValueError("boom")

    resp = asyncio.run(ep.openai_chat(_BadReq(None)))
    data = _body(resp)
    assert resp.status_code == 400
    assert isinstance(data["error"], dict)
    assert data["error"]["message"] == "Invalid JSON payload"
    assert data["error"]["type"] == "invalid_request_error"


def test_anon_callers_get_isolated_sessions():
    gw = _FakeGateway()
    ep = GatewayApiEndpoints(gw)
    req = _FakeReq(
        {"model": "assistant", "messages": [{"role": "user", "content": "x"}]}
    )
    asyncio.run(ep.openai_chat(req))
    asyncio.run(ep.openai_chat(req))
    # No session header + no bearer token -> unique keys, never a shared session.
    assert gw.created_sessions[0][1] != gw.created_sessions[1][1]


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


def test_openai_chat_reports_real_usage():
    ep = GatewayApiEndpoints(_FakeGateway())
    resp = asyncio.run(
        ep.openai_chat(
            _FakeReq(
                {"model": "assistant", "messages": [{"role": "user", "content": "hi"}]}
            )
        )
    )
    usage = _body(resp)["usage"]
    assert usage["prompt_tokens"] == 11
    assert usage["completion_tokens"] == 7
    assert usage["total_tokens"] == 18


def test_openai_chat_usage_zero_when_no_metrics():
    class _NoMetricsAgent:
        async def achat(self, content):
            return f"echo:{content}"

    class _Gw(_FakeGateway):
        def __init__(self):
            super().__init__()
            self._agent = _NoMetricsAgent()

    ep = GatewayApiEndpoints(_Gw())
    resp = asyncio.run(
        ep.openai_chat(
            _FakeReq(
                {"model": "assistant", "messages": [{"role": "user", "content": "hi"}]}
            )
        )
    )
    usage = _body(resp)["usage"]
    assert usage == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def _collect_sse(resp):
    async def _run():
        chunks = []
        async for part in resp.body_iterator:
            chunks.append(part if isinstance(part, str) else part.decode())
        return chunks

    return asyncio.run(_run())


def test_openai_chat_stream_emits_usage_chunk_when_opted_in():
    ep = GatewayApiEndpoints(_FakeGateway())
    resp = asyncio.run(
        ep.openai_chat(
            _FakeReq(
                {
                    "model": "assistant",
                    "stream": True,
                    "stream_options": {"include_usage": True},
                    "messages": [{"role": "user", "content": "hi"}],
                }
            )
        )
    )
    parts = _collect_sse(resp)
    usage_payloads = [
        json.loads(p[len("data: "):])
        for p in parts
        if p.startswith("data: ") and '"usage"' in p
    ]
    assert usage_payloads, "expected a usage-bearing chunk"
    usage = usage_payloads[-1]["usage"]
    assert usage["prompt_tokens"] == 11
    assert usage["completion_tokens"] == 7
    assert usage["total_tokens"] == 18
    assert parts[-1] == "data: [DONE]\n\n"


def test_openai_chat_stream_omits_usage_by_default():
    ep = GatewayApiEndpoints(_FakeGateway())
    resp = asyncio.run(
        ep.openai_chat(
            _FakeReq(
                {
                    "model": "assistant",
                    "stream": True,
                    "messages": [{"role": "user", "content": "hi"}],
                }
            )
        )
    )
    parts = _collect_sse(resp)
    assert not any('"usage"' in p for p in parts)
    assert parts[-1] == "data: [DONE]\n\n"


def test_dispatch_binds_usage_snapshot_to_its_turn():
    # ``_dispatch`` must return the token usage snapshotted atomically with the
    # turn result. A later overwrite of the shared, mutable ``last_token_metrics``
    # (as a concurrent turn on the same Agent would do) must not change the
    # already-returned snapshot.
    class _MutableMetrics:
        def __init__(self, i, o):
            self.input_tokens = i
            self.output_tokens = o

    class _SharedLLM:
        def __init__(self):
            self.last_token_metrics = _MutableMetrics(11, 7)

    class _SharedAgent:
        def __init__(self):
            self._llm_instance = _SharedLLM()

        async def achat(self, content):
            return f"echo:{content}"

    class _Gw(_FakeGateway):
        def __init__(self):
            super().__init__()
            self._agent = _SharedAgent()

    gw = _Gw()
    ep = GatewayApiEndpoints(gw)
    reply, usage = asyncio.run(
        ep._dispatch(_FakeSession(), gw._agent, "hi")
    )
    # Mutate the shared metric AFTER dispatch returned its snapshot.
    gw._agent._llm_instance.last_token_metrics = _MutableMetrics(999, 999)
    assert reply == "echo:hi"
    assert usage == {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}


def test_stream_usage_snapshot_survives_concurrent_overwrite():
    # The SSE generator yields (suspends) several frames after the turn before
    # emitting the usage chunk. While suspended, a concurrent turn on the same
    # shared Agent can overwrite ``last_token_metrics``. The streamed usage must
    # still reflect THIS turn (snapshotted at dispatch), not the overwrite.
    class _MutableMetrics:
        def __init__(self, i, o):
            self.input_tokens = i
            self.output_tokens = o

    class _SharedLLM:
        def __init__(self):
            self.last_token_metrics = _MutableMetrics(11, 7)

    class _SharedAgent:
        def __init__(self):
            self._llm_instance = _SharedLLM()

        async def achat(self, content):
            return f"echo:{content}"

    class _Gw(_FakeGateway):
        def __init__(self):
            super().__init__()
            self._agent = _SharedAgent()

    gw = _Gw()
    ep = GatewayApiEndpoints(gw)
    resp = asyncio.run(
        ep.openai_chat(
            _FakeReq(
                {
                    "model": "assistant",
                    "stream": True,
                    "stream_options": {"include_usage": True},
                    "messages": [{"role": "user", "content": "hi"}],
                }
            )
        )
    )

    async def _drain_with_overwrite():
        parts = []
        async for part in resp.body_iterator:
            text = part if isinstance(part, str) else part.decode()
            parts.append(text)
            # Once the assistant content frame has streamed (i.e. the turn has
            # already completed and been snapshotted), simulate a *concurrent*
            # turn overwriting the shared, mutable metric before the usage frame.
            if '"content"' in text:
                gw._agent._llm_instance.last_token_metrics = _MutableMetrics(
                    999, 999
                )
        return parts

    parts = asyncio.run(_drain_with_overwrite())
    usage_payloads = [
        json.loads(p[len("data: "):])
        for p in parts
        if p.startswith("data: ") and '"usage"' in p
    ]
    assert usage_payloads, "expected a usage-bearing chunk"
    usage = usage_payloads[-1]["usage"]
    # Snapshotted at dispatch -> original counts, not the mid-stream overwrite.
    assert usage == {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}


def test_sync_agent_usage_snapshot_captured_before_thread_returns():
    # Greptile/Qodo P1 (sync fallback): a sync-only agent's ``chat`` runs in a
    # worker THREAD. A bare read AFTER the executor ``await`` resolves is NOT
    # atomic with the turn — the "no intervening await" guarantee only orders
    # event-loop coroutines, not worker threads — so a concurrent turn can
    # overwrite the shared, mutable ``last_token_metrics`` in the window between
    # the turn's ``chat`` returning and the handler reading it. The real
    # gateway's ``_dispatch_agent_turn`` must therefore snapshot INSIDE the
    # worker thread, before it returns, via ``on_complete``. We assert exactly
    # that ordering against the real server method.
    from praisonai_bot.gateway.server import WebSocketGateway

    events: list = []

    class _Metrics:
        input_tokens = 11
        output_tokens = 7

    class _LLM:
        last_token_metrics = _Metrics()

    class _SyncAgent:
        # No ``arun``/``achat`` -> forces the sync ``chat`` executor path.
        _llm_instance = _LLM()

        def chat(self, content):
            events.append("chat_returned")
            return f"echo:{content}"

    def _capture(a):
        # Records that the snapshot ran, and its ordering vs ``chat`` return.
        events.append("snapshot")

    reply = asyncio.run(
        WebSocketGateway._dispatch_agent_turn(
            _SyncAgent(), "hi", on_complete=_capture
        )
    )
    assert reply == "echo:hi"
    # The snapshot must fire in the SAME worker-thread context, immediately
    # after ``chat`` returns and before the future resolves back on the loop —
    # so ``chat_returned`` is immediately followed by ``snapshot`` with no gap
    # a concurrent turn could exploit.
    assert events == ["chat_returned", "snapshot"]


def test_openai_responses_reports_usage():
    ep = GatewayApiEndpoints(_FakeGateway())
    resp = asyncio.run(
        ep.openai_responses(_FakeReq({"model": "assistant", "input": "ping"}))
    )
    usage = _body(resp)["usage"]
    assert usage["input_tokens"] == 11
    assert usage["output_tokens"] == 7
    assert usage["total_tokens"] == 18


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
