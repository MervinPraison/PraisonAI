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
    async def _dispatch_agent_turn(agent, content, on_complete=None, interrupt=None):
        result = await agent.achat(content)
        # Mirror the real gateway: snapshot per-turn state in the same context
        # that produced the result, before returning to the caller.
        if on_complete is not None:
            on_complete(agent)
        return result


class _FakeReq:
    def __init__(self, body, headers=None, path_params=None):
        self._body = body
        self.headers = headers or {}
        self.path_params = path_params or {}

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


class _RealEmitterAgent:
    """Agent whose ``achat`` emits real DELTA_TEXT events via a stream_emitter."""

    def __init__(self, deltas):
        from praisonaiagents.streaming.events import StreamEventEmitter

        self.stream_emitter = StreamEventEmitter()
        self._llm_instance = _FakeLLM()
        self._deltas = deltas

    async def achat(self, content):
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType

        for piece in self._deltas:
            self.stream_emitter.emit(
                StreamEvent(type=StreamEventType.DELTA_TEXT, content=piece)
            )
            await asyncio.sleep(0)
        return "".join(self._deltas)


class _StreamGateway(_FakeGateway):
    """Gateway with token streaming enabled and a delta-emitting agent."""

    def __init__(self, deltas=("Hel", "lo ", "world")):
        super().__init__()
        self._agent = _RealEmitterAgent(list(deltas))

        class _Api:
            stream = True

        class _Cfg:
            api = _Api()

        self.config = _Cfg()


def _content_texts(parts):
    out = []
    for p in parts:
        if p.startswith("data: ") and '"content"' in p:
            payload = json.loads(p[len("data: "):])
            out.append(payload["choices"][0]["delta"]["content"])
    return out


def test_stream_enabled_emits_token_level_deltas():
    gw = _StreamGateway(deltas=("Hel", "lo ", "world"))
    ep = GatewayApiEndpoints(gw)
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
    # Each token delta arrives as its own content frame (not one buffered chunk).
    assert _content_texts(parts) == ["Hel", "lo ", "world"]
    assert parts[-1] == "data: [DONE]\n\n"
    # Terminator + role prelude preserved.
    assert any('"finish_reason": "stop"' in p for p in parts)
    assert any('"role": "assistant"' in p for p in parts)


def test_stream_enabled_still_emits_usage_when_opted_in():
    gw = _StreamGateway()
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
    parts = _collect_sse(resp)
    usage_payloads = [
        json.loads(p[len("data: "):])
        for p in parts
        if p.startswith("data: ") and '"usage"' in p
    ]
    assert usage_payloads
    assert usage_payloads[-1]["usage"]["total_tokens"] == 18


def test_stream_enabled_falls_back_to_buffered_when_no_deltas():
    # An agent that streams no DELTA_TEXT must still deliver its reply as one
    # buffered content chunk so content is never lost.
    gw = _StreamGateway(deltas=())
    ep = GatewayApiEndpoints(gw)

    async def _achat(content):
        return "buffered-reply"

    gw._agent.achat = _achat
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
    assert _content_texts(parts) == ["buffered-reply"]
    assert parts[-1] == "data: [DONE]\n\n"


def test_stream_disabled_uses_single_buffered_chunk():
    # Default gateway (no config.api.stream) keeps the byte-for-byte buffered
    # path: one content chunk carrying the whole reply.
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
    assert _content_texts(parts) == ["echo:hi"]
    assert parts[-1] == "data: [DONE]\n\n"


def test_api_config_stream_roundtrip():
    from praisonaiagents.gateway import ApiConfig

    assert ApiConfig().stream is False
    cfg = ApiConfig.from_dict({"openai": True, "stream": True})
    assert cfg.stream is True
    assert cfg.to_dict()["stream"] is True


class _FirstTokenAgent:
    """Agent whose first answer piece is a FIRST_TOKEN event, rest DELTA_TEXT.

    Mirrors the real SDK, which marks the opening content piece with
    ``FIRST_TOKEN`` (the TTFT marker) and only subsequent pieces with
    ``DELTA_TEXT``. It also emits a reasoning delta that must NOT surface as
    answer text.
    """

    def __init__(self):
        from praisonaiagents.streaming.events import StreamEventEmitter

        self.stream_emitter = StreamEventEmitter()
        self._llm_instance = _FakeLLM()

    async def achat(self, content):
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType

        # Private reasoning first — must be filtered out of the answer stream.
        self.stream_emitter.emit(
            StreamEvent(
                type=StreamEventType.DELTA_TEXT,
                content="(thinking...)",
                is_reasoning=True,
            )
        )
        await asyncio.sleep(0)
        self.stream_emitter.emit(
            StreamEvent(type=StreamEventType.FIRST_TOKEN, content="Hel")
        )
        await asyncio.sleep(0)
        self.stream_emitter.emit(
            StreamEvent(type=StreamEventType.DELTA_TEXT, content="lo")
        )
        await asyncio.sleep(0)
        return "Hello"


def test_stream_includes_first_token_and_drops_reasoning():
    # Greptile P1: the opening FIRST_TOKEN piece must be delivered (not lost to
    # the buffered fallback) and reasoning deltas must never leak as answer text.
    gw = _StreamGateway()
    gw._agent = _FirstTokenAgent()
    ep = GatewayApiEndpoints(gw)
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
    texts = _content_texts(parts)
    # First token present, ordered before the later delta, reasoning excluded.
    assert texts == ["Hel", "lo"]
    assert "(thinking...)" not in "".join(texts)
    assert parts[-1] == "data: [DONE]\n\n"


def test_stream_empty_reply_still_emits_content_frame():
    # Greptile P2: an empty reply with no deltas must still carry a content
    # frame so the frame shape matches the buffered single-chunk path exactly.
    gw = _StreamGateway(deltas=())
    ep = GatewayApiEndpoints(gw)

    async def _achat(content):
        return ""

    gw._agent.achat = _achat
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
    # Exactly one content frame carrying the empty string.
    assert _content_texts(parts) == [""]
    assert parts[-1] == "data: [DONE]\n\n"


def test_stream_delivers_frames_incrementally_before_turn_completes():
    # Greptile P2: the whole point of streaming is time-to-first-token. This
    # asserts a token's SSE frame is available BEFORE the turn finishes, not
    # only after the agent returns its full reply. The agent blocks after the
    # first delta until the consumer has observed that delta's frame.
    from praisonaiagents.streaming.events import (
        StreamEvent,
        StreamEventEmitter,
        StreamEventType,
    )

    first_frame_seen = asyncio.Event()

    class _PausingAgent:
        def __init__(self):
            self.stream_emitter = StreamEventEmitter()
            self._llm_instance = _FakeLLM()
            self.completed = False

        async def achat(self, content):
            self.stream_emitter.emit(
                StreamEvent(type=StreamEventType.DELTA_TEXT, content="early")
            )
            # Do not finish the turn until the consumer has seen the frame.
            await first_frame_seen.wait()
            self.completed = True
            return "early-late"

    gw = _StreamGateway()
    agent = _PausingAgent()
    gw._agent = agent
    ep = GatewayApiEndpoints(gw)

    def part_is_content(text, needle):
        return text.startswith("data: ") and '"content"' in text and needle in text

    async def _run():
        response = await ep.openai_chat(
            _FakeReq(
                {
                    "model": "assistant",
                    "stream": True,
                    "messages": [{"role": "user", "content": "hi"}],
                }
            )
        )
        seen = []
        async for part in response.body_iterator:
            text = part if isinstance(part, str) else part.decode()
            if part_is_content(text, "early"):
                # We received the first token's frame while the turn is still
                # paused (not yet completed) — genuine incremental delivery.
                assert agent.completed is False
                first_frame_seen.set()
            seen.append(text)
        return seen

    parts = asyncio.run(_run())
    assert agent.completed is True
    assert "early" in "".join(_content_texts(parts))
    assert parts[-1] == "data: [DONE]\n\n"


def test_concurrent_streams_do_not_mix_caller_text():
    # Greptile P1 (security): two callers streaming from the SAME agent
    # instance (shared stream_emitter) must each receive only their own tokens.
    # The per-turn ContextVar isolation must keep the fan-out separated.
    from praisonaiagents.streaming.events import (
        StreamEvent,
        StreamEventEmitter,
        StreamEventType,
    )

    class _TaggingAgent:
        """Emits deltas tagged with the calling turn's content prefix."""

        def __init__(self):
            self.stream_emitter = StreamEventEmitter()
            self._llm_instance = _FakeLLM()

        async def achat(self, content):
            # Two deltas, each prefixed with this turn's content so a leak
            # between callers is detectable.
            for i in range(3):
                self.stream_emitter.emit(
                    StreamEvent(
                        type=StreamEventType.DELTA_TEXT,
                        content=f"{content}-{i}",
                    )
                )
                await asyncio.sleep(0)
            return content

    gw = _StreamGateway()
    gw._agent = _TaggingAgent()
    ep = GatewayApiEndpoints(gw)

    async def _one(marker):
        response = await ep.openai_chat(
            _FakeReq(
                {
                    "model": "assistant",
                    "stream": True,
                    "messages": [{"role": "user", "content": marker}],
                }
            )
        )
        parts = []
        async for part in response.body_iterator:
            parts.append(part if isinstance(part, str) else part.decode())
        return _content_texts(parts)

    async def _run():
        return await asyncio.gather(_one("AAA"), _one("BBB"))

    a_texts, b_texts = asyncio.run(_run())
    # Each stream only carries its own marker — no cross-contamination.
    assert all(t.startswith("AAA") for t in a_texts), a_texts
    assert all(t.startswith("BBB") for t in b_texts), b_texts


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


# ── Issue #5335: background/async runs ─────────────────────────────────


def _run_background_flow(gw, ep, body):
    """Submit a background response and drain the driving task on one loop."""

    async def _flow():
        submit = await ep.openai_responses(_FakeReq(body))
        data = _body(submit)
        # Let the spawned task run to completion on this loop.
        entry = ep._responses[data["id"]]
        task = entry.get("task")
        if task is not None:
            await task
        return submit, data

    return asyncio.run(_flow())


def test_background_submission_returns_queued_202():
    gw = _FakeGateway()
    ep = GatewayApiEndpoints(gw)
    submit, data = _run_background_flow(
        gw, ep, {"model": "assistant", "input": "ping", "background": True}
    )
    assert submit.status_code == 202
    assert data["status"] == "queued"
    assert data["object"] == "response"
    assert data["id"].startswith("resp-")
    # Persisted and retrievable by id.
    assert data["id"] in ep._responses


def test_background_run_completes_and_is_retrievable():
    gw = _FakeGateway()
    ep = GatewayApiEndpoints(gw)
    _submit, data = _run_background_flow(
        gw, ep, {"model": "assistant", "input": "ping", "store": True}
    )
    got = asyncio.run(
        ep.openai_responses_get(_FakeReq(None, path_params={"id": data["id"]}))
    )
    body = _body(got)
    assert body["status"] == "completed"
    assert body["output_text"] == "echo:ping"
    assert body["usage"]["input_tokens"] == 11


def test_synchronous_responses_still_default():
    # No background/store -> unchanged synchronous behaviour (status completed).
    ep = GatewayApiEndpoints(_FakeGateway())
    resp = asyncio.run(
        ep.openai_responses(_FakeReq({"model": "assistant", "input": "ping"}))
    )
    data = _body(resp)
    assert data["status"] == "completed"
    assert data["output_text"] == "echo:ping"


def test_get_unknown_response_returns_404():
    ep = GatewayApiEndpoints(_FakeGateway())
    resp = asyncio.run(
        ep.openai_responses_get(_FakeReq(None, path_params={"id": "resp-nope"}))
    )
    assert resp.status_code == 404
    assert _body(resp)["error"]["type"] == "invalid_request_error"


def test_cancel_unknown_response_returns_404():
    ep = GatewayApiEndpoints(_FakeGateway())
    resp = asyncio.run(
        ep.openai_responses_cancel(_FakeReq(None, path_params={"id": "resp-nope"}))
    )
    assert resp.status_code == 404


def test_completed_empty_reply_still_has_message_output():
    # Greptile P1: a completed sync response with empty text must still carry an
    # assistant message so clients that read output[0] keep working.
    class _EmptyAgent:
        _llm_instance = _FakeLLM()

        async def achat(self, content):
            return ""

    class _Gw(_FakeGateway):
        def __init__(self):
            super().__init__()
            self._agent = _EmptyAgent()

    ep = GatewayApiEndpoints(_Gw())
    resp = asyncio.run(
        ep.openai_responses(_FakeReq({"model": "assistant", "input": "x"}))
    )
    data = _body(resp)
    assert data["status"] == "completed"
    assert data["output_text"] == ""
    assert len(data["output"]) == 1
    assert data["output"][0]["role"] == "assistant"
    assert data["output"][0]["content"][0]["text"] == ""


def test_retrieval_message_id_stable_across_polls():
    # Greptile P2: polling a completed background response must return the same
    # output message id each time.
    gw = _FakeGateway()
    ep = GatewayApiEndpoints(gw)
    _submit, data = _run_background_flow(
        gw, ep, {"model": "assistant", "input": "ping", "store": True}
    )

    def _get():
        return _body(
            asyncio.run(
                ep.openai_responses_get(
                    _FakeReq(None, path_params={"id": data["id"]})
                )
            )
        )

    first = _get()
    second = _get()
    assert first["output"][0]["id"] == second["output"][0]["id"]


def test_retrieval_scoped_to_owner_for_stable_callers():
    # Greptile P1 security: a run submitted under one bearer token must not be
    # retrievable by a different token.
    gw = _FakeGateway()
    ep = GatewayApiEndpoints(gw)

    async def _flow():
        submit = await ep.openai_responses(
            _FakeReq(
                {"model": "assistant", "input": "ping", "store": True},
                headers={"authorization": "Bearer alice-secret-token"},
            )
        )
        rid = _body(submit)["id"]
        task = ep._responses[rid].get("task")
        if task is not None:
            await task
        return rid

    rid = asyncio.run(_flow())

    # Owner (same token) can read it.
    owner_get = asyncio.run(
        ep.openai_responses_get(
            _FakeReq(
                None,
                headers={"authorization": "Bearer alice-secret-token"},
                path_params={"id": rid},
            )
        )
    )
    assert _body(owner_get)["status"] == "completed"

    # A different token is denied (404, not leaking existence).
    other_get = asyncio.run(
        ep.openai_responses_get(
            _FakeReq(
                None,
                headers={"authorization": "Bearer mallory-other-token"},
                path_params={"id": rid},
            )
        )
    )
    assert other_get.status_code == 404


def test_rejected_background_run_marked_failed_not_completed():
    # Greptile P1: an admission-gate rejection must surface as ``failed`` so a
    # poller never mistakes the busy message for a successful result.
    from praisonai_bot.bots._admission import AdmissionRejected

    class _RejectingGate:
        enabled = True

        def admit(self, session_id=None):
            gate = self

            class _Ctx:
                async def __aenter__(self):
                    raise AdmissionRejected("gateway busy")

                async def __aexit__(self, *exc):
                    return False

            return _Ctx()

    class _Gw(_FakeGateway):
        def __init__(self):
            super().__init__()
            self._admission_gate = _RejectingGate()

    gw = _Gw()
    ep = GatewayApiEndpoints(gw)
    _submit, data = _run_background_flow(
        gw, ep, {"model": "assistant", "input": "x", "background": True}
    )
    got = _body(
        asyncio.run(
            ep.openai_responses_get(_FakeReq(None, path_params={"id": data["id"]}))
        )
    )
    assert got["status"] == "failed"
    assert "busy" in (got.get("error", {}) or {}).get("message", "")


def test_store_evicts_oldest_terminal_when_full():
    # Greptile P1: the in-process store is bounded; terminal entries are evicted
    # oldest-first once at capacity so memory cannot grow without bound.
    gw = _FakeGateway()
    ep = GatewayApiEndpoints(gw)
    ep._responses_max = 3

    ids = []
    for _ in range(5):
        _submit, data = _run_background_flow(
            gw, ep, {"model": "assistant", "input": "ping", "store": True}
        )
        ids.append(data["id"])

    assert len(ep._responses) <= 3
    # The most recent submissions are retained; the oldest were evicted.
    assert ids[-1] in ep._responses
    assert ids[0] not in ep._responses


def test_cancel_in_flight_background_run():
    # A run that never completes on its own must flip to ``cancelled`` when the
    # cancel route fires (cooperative controller + task cancel).
    class _SlowAgent:
        _llm_instance = _FakeLLM()

        async def achat(self, content):
            await asyncio.sleep(60)
            return f"echo:{content}"

    class _Gw(_FakeGateway):
        def __init__(self):
            super().__init__()
            self._agent = _SlowAgent()

        @staticmethod
        async def _dispatch_agent_turn(agent, content, on_complete=None, interrupt=None):
            result = await agent.achat(content)
            if on_complete is not None:
                on_complete(agent)
            return result

    async def _flow():
        gw = _Gw()
        ep = GatewayApiEndpoints(gw)
        submit = await ep.openai_responses(
            _FakeReq({"model": "assistant", "input": "x", "background": True})
        )
        rid = _body(submit)["id"]
        await asyncio.sleep(0)  # let the task start and suspend on sleep
        cancel = await ep.openai_responses_cancel(
            _FakeReq(None, path_params={"id": rid})
        )
        return _body(cancel)

    data = asyncio.run(_flow())
    assert data["status"] == "cancelled"
