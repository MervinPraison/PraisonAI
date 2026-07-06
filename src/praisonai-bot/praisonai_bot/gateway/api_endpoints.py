"""OpenAI-compatible and MCP protocol surfaces for the gateway.

These are *additive*, config-gated Starlette routes mounted on the same app
and protected by the same auth token as ``/info``/``/metrics``. Every request
is dispatched into the gateway's own registered agents and shares the gateway's
session store and inbound admission gate, so an OpenAI-SDK client, an MCP
client and the chat channels all reach the *same* stateful agent.

The handlers are intentionally kept out of ``server.py`` so the gateway server
module does not grow. They receive the live ``WebSocketGateway`` instance and
call back into its public/registered state (``list_agents``, ``get_agent``,
``create_session``, admission gate, ``_dispatch_agent_turn``).
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, List, Optional


def _now() -> int:
    return int(time.time())


def _msg_content(msg: Any) -> str:
    """Extract the plain-text content from one OpenAI message dict."""
    content = msg.get("content", "") if isinstance(msg, dict) else ""
    if isinstance(content, list):
        # OpenAI content-part arrays -> concatenate text parts.
        content = "".join(
            p.get("text", "")
            for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        )
    return str(content or "")


def _extract_text(messages: Any) -> str:
    """Collapse an OpenAI ``messages`` array into a single agent turn.

    The gateway agent owns conversation memory via its session, so for a plain
    single-turn request (system + one user message) we forward just the latest
    user content and let the gateway's own history supply prior context.

    However, standard OpenAI-SDK clients are stateless and resend the *entire*
    conversation (assistant turns included) on every request. Dropping those
    turns would make the agent answer without the context the caller supplied.
    So when the array carries assistant turns (externally-built history), we
    forward a labelled transcript of the full exchange instead of only the last
    user line — no context is silently lost (Issue #2715 review, Greptile P1).
    """
    if not isinstance(messages, list):
        return str(messages or "")

    system_parts: List[str] = []
    turns: List[tuple] = []  # (role, text) for user/assistant turns
    has_assistant = False
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = _msg_content(msg)
        if role == "system":
            system_parts.append(content)
        elif role == "assistant":
            has_assistant = True
            turns.append(("assistant", content))
        elif role == "user":
            turns.append(("user", content))

    if not has_assistant:
        # Single logical turn: forward the last user line; the gateway session
        # holds any prior context from earlier turns it already handled.
        last_user = next(
            (t for r, t in reversed(turns) if r == "user"), ""
        )
        if system_parts:
            return "\n".join(system_parts + [last_user]).strip()
        return last_user

    # Externally-supplied history: preserve the full exchange so the agent has
    # every prior turn the caller sent, even on a brand-new gateway session.
    lines: List[str] = list(system_parts)
    for role, text in turns:
        label = "User" if role == "user" else "Assistant"
        lines.append(f"{label}: {text}")
    return "\n".join(lines).strip()


class GatewayApiEndpoints:
    """Adapter exposing OpenAI-compatible + MCP surfaces over a gateway."""

    def __init__(self, gateway: Any) -> None:
        self._gw = gateway

    # ── shared dispatch ────────────────────────────────────────────────
    def _resolve_agent(self, requested: Optional[str]):
        """Resolve the target agent id/instance for a request.

        Prefers an explicit model/agent id; falls back to the first
        registered agent so ``model="assistant"`` style calls just work.
        """
        agents = self._gw.list_agents()
        if not agents:
            return None, None
        if requested and requested in agents:
            return requested, self._gw.get_agent(requested)
        aid = agents[0]
        return aid, self._gw.get_agent(aid)

    async def _dispatch(self, session: Any, agent: Any, content: str) -> str:
        """Run one agent turn through the same admission gate as chat users."""
        gate = getattr(self._gw, "_admission_gate", None)
        if gate is not None and getattr(gate, "enabled", False):
            from ..bots._admission import AdmissionRejected
            try:
                async with gate.admit(session_id=session.session_id):
                    result = await self._gw._dispatch_agent_turn(agent, content)
            except AdmissionRejected as rej:
                return str(rej.message)
        else:
            result = await self._gw._dispatch_agent_turn(agent, content)
        return "" if result is None else str(result)

    def _session_for(self, agent_id: str, key: str) -> Any:
        """Get or create a stable session keyed by the API caller."""
        session_id = f"api:{key}:{agent_id}"
        return self._gw.create_session(agent_id=agent_id, session_id=session_id)

    @staticmethod
    def _caller_key(request: Any) -> str:
        """Derive a stable per-caller session key from the request.

        Uses an ``OpenAI-Session``/``X-Session-Id`` header when supplied so a
        client can pin a conversation; otherwise falls back to the bearer
        token (shared operator) so repeated calls reuse one agent session.

        With no session header and no bearer token (e.g. auth disabled), we mint
        a fresh unique key per request rather than a shared literal so unrelated
        callers never land in the *same* agent session and silently share memory
        (Issue #2715 review, Greptile P2). Such callers are stateless by design;
        they should pass a session header to pin a conversation.
        """
        for header in ("openai-session", "x-session-id"):
            val = request.headers.get(header)
            if val:
                return val
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            return "token:" + auth[7:][:16]
        return "anon:" + uuid.uuid4().hex

    @staticmethod
    def _openai_error(message: str, status_code: int, err_type: str):
        """Return an OpenAI-spec error body ``{"error": {message, type, code}}``.

        The OpenAI Python SDK reads ``error.message`` from the parsed body, so a
        bare string ``error`` field yields an empty message on the client side
        (Issue #2715 review, Greptile P2).
        """
        from starlette.responses import JSONResponse

        return JSONResponse(
            {
                "error": {
                    "message": message,
                    "type": err_type,
                    "code": None,
                    "param": None,
                }
            },
            status_code=status_code,
        )

    # ── OpenAI: models ─────────────────────────────────────────────────
    async def openai_models(self, request):
        from starlette.responses import JSONResponse
        data = [
            {"id": aid, "object": "model", "created": _now(), "owned_by": "praisonai"}
            for aid in self._gw.list_agents()
        ]
        return JSONResponse({"object": "list", "data": data})

    # ── OpenAI: chat completions ───────────────────────────────────────
    async def openai_chat(self, request):
        from starlette.responses import JSONResponse

        try:
            body = await request.json()
        except ValueError:
            return self._openai_error(
                "Invalid JSON payload", 400, "invalid_request_error"
            )
        if not isinstance(body, dict):
            return self._openai_error(
                "Expected a JSON object", 400, "invalid_request_error"
            )

        agent_id, agent = self._resolve_agent(body.get("model"))
        if agent is None:
            return self._openai_error(
                "No agents registered on this gateway", 503, "server_error"
            )

        content = _extract_text(body.get("messages"))
        session = self._session_for(agent_id, self._caller_key(request))
        stream = bool(body.get("stream"))
        completion_id = "chatcmpl-" + uuid.uuid4().hex

        if stream:
            return self._sse_chat(agent_id, agent, session, content, completion_id)

        reply = await self._dispatch(session, agent, content)
        return JSONResponse(
            {
                "id": completion_id,
                "object": "chat.completion",
                "created": _now(),
                "model": agent_id,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": reply},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            }
        )

    def _sse_chat(self, agent_id, agent, session, content, completion_id):
        """Emit a spec-shaped SSE chat-completion stream.

        The frames are correctly ``chat.completion.chunk`` shaped and terminate
        with ``[DONE]`` so any OpenAI streaming client parses them. The content
        is delivered as a single chunk once the agent turn completes (buffered)
        rather than token-by-token: true incremental token streaming would need
        the agent's ``stream_emitter`` wired through the gateway hot path, which
        is deliberately out of scope here to avoid a hot-path regression. Latency
        to first *content* therefore matches non-streaming; response correctness
        and client compatibility are unaffected.
        """
        from starlette.responses import StreamingResponse

        async def gen():
            created = _now()
            first = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": agent_id,
                "choices": [
                    {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}
                ],
            }
            yield f"data: {json.dumps(first)}\n\n"

            reply = await self._dispatch(session, agent, content)
            chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": agent_id,
                "choices": [
                    {"index": 0, "delta": {"content": reply}, "finish_reason": None}
                ],
            }
            yield f"data: {json.dumps(chunk)}\n\n"

            final = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": agent_id,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(final)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    # ── OpenAI: responses ──────────────────────────────────────────────
    async def openai_responses(self, request):
        from starlette.responses import JSONResponse

        try:
            body = await request.json()
        except ValueError:
            return self._openai_error(
                "Invalid JSON payload", 400, "invalid_request_error"
            )
        if not isinstance(body, dict):
            return self._openai_error(
                "Expected a JSON object", 400, "invalid_request_error"
            )

        agent_id, agent = self._resolve_agent(body.get("model"))
        if agent is None:
            return self._openai_error(
                "No agents registered on this gateway", 503, "server_error"
            )

        # ``input`` may be a plain string or an OpenAI messages-style array.
        raw = body.get("input", "")
        content = raw if isinstance(raw, str) else _extract_text(raw)
        session = self._session_for(agent_id, self._caller_key(request))
        reply = await self._dispatch(session, agent, content)

        return JSONResponse(
            {
                "id": "resp-" + uuid.uuid4().hex,
                "object": "response",
                "created_at": _now(),
                "model": agent_id,
                "status": "completed",
                "output": [
                    {
                        "id": "msg-" + uuid.uuid4().hex,
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": reply}],
                    }
                ],
                "output_text": reply,
            }
        )

    # ── MCP: JSON-RPC ──────────────────────────────────────────────────
    async def mcp_jsonrpc(self, request):
        from starlette.responses import JSONResponse

        try:
            body = await request.json()
        except ValueError:
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                },
                status_code=400,
            )

        rpc_id = body.get("id") if isinstance(body, dict) else None
        method = body.get("method") if isinstance(body, dict) else None
        params = body.get("params", {}) if isinstance(body, dict) else {}

        def ok(result):
            return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": result})

        def err(code, message):
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {"code": code, "message": message},
                }
            )

        if method == "initialize":
            return ok(
                {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "PraisonAI Gateway", "version": "1.0.0"},
                    "capabilities": {"tools": {}},
                }
            )

        if method in ("notifications/initialized", "ping"):
            return ok({})

        if method == "tools/list":
            tools = [
                {
                    "name": aid,
                    "description": f"Dispatch a message to gateway agent '{aid}'",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string",
                                "description": "The message to send to the agent",
                            }
                        },
                        "required": ["message"],
                    },
                }
                for aid in self._gw.list_agents()
            ]
            return ok({"tools": tools})

        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {}) or {}
            agent_id, agent = self._resolve_agent(name)
            if agent is None:
                return err(-32602, f"Unknown agent/tool: {name}")
            content = str(arguments.get("message", ""))
            session = self._session_for(agent_id, self._caller_key(request))
            reply = await self._dispatch(session, agent, content)
            return ok(
                {
                    "content": [{"type": "text", "text": reply}],
                    "isError": False,
                }
            )

        return err(-32601, f"Method not found: {method}")
