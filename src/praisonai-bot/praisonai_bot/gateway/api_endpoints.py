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

import asyncio
import contextvars
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

    async def _dispatch(self, session: Any, agent: Any, content: str) -> tuple:
        """Run one agent turn through the same admission gate as chat users.

        Returns ``(reply, usage)`` where ``usage`` is a snapshot of the agent's
        per-turn token metrics captured **in the same execution context that
        produced the turn's result**.

        One ``Agent`` instance can serve overlapping turns for several sessions.
        The SDK stores per-turn counts on a *shared, mutable*
        ``llm.last_token_metrics`` reference that each turn overwrites, so any
        read that is not bound to the completing turn's own context can report a
        different concurrent request's counts. The native async path runs on the
        single event loop (no cross-turn interleaving without an ``await``), but
        the sync ``chat`` fallback runs in a worker **thread**, so a bare read
        after the ``await`` could still observe another thread's overwrite
        (Greptile/Qodo P1). We therefore hand ``_dispatch_agent_turn`` an
        ``on_complete`` callback that snapshots the metrics *inside that same
        context* — the worker thread for sync agents, the loop tick for async —
        before it can be clobbered.
        """
        holder: dict = {}

        def _capture(a: Any) -> None:
            holder["usage"] = self._usage_for(a)

        gate = getattr(self._gw, "_admission_gate", None)
        if gate is not None and getattr(gate, "enabled", False):
            from ..bots._admission import AdmissionRejected
            try:
                async with gate.admit(session_id=session.session_id):
                    result = await self._gw._dispatch_agent_turn(
                        agent, content, on_complete=_capture
                    )
            except AdmissionRejected as rej:
                return str(rej.message), self._zero_usage()
        else:
            result = await self._gw._dispatch_agent_turn(
                agent, content, on_complete=_capture
            )
        usage = holder.get("usage") or self._zero_usage()
        return ("" if result is None else str(result)), usage

    def _streaming_enabled(self) -> bool:
        """Whether token-level SSE streaming is opted in via ``gateway.api.stream``.

        Off by default so the streaming surface stays byte-for-byte the buffered
        single-chunk path until an operator explicitly enables it.
        """
        cfg = getattr(self._gw, "config", None)
        api = getattr(cfg, "api", None)
        return bool(getattr(api, "stream", False))

    # Task-local marker so a stream callback only forwards events emitted by
    # *its own* turn. One ``Agent`` instance (hence one shared
    # ``stream_emitter``) can serve overlapping turns for several callers; the
    # emitter fans every event out to every registered callback with no turn
    # identity. Without isolation, caller A's SSE stream would receive caller
    # B's tokens (Greptile P1 — concurrent streams mix caller text). The turn's
    # execution context (native async task, or the copied context that
    # ``asyncio.to_thread`` runs a sync agent under) carries this token, so a
    # callback compares the running turn's token to the one it was created for
    # and drops foreign events.
    _stream_turn_var: "contextvars.ContextVar[Optional[object]]" = (
        contextvars.ContextVar("praisonai_gw_stream_turn", default=None)
    )

    async def _dispatch_stream(self, session: Any, agent: Any, content: str):
        """Run one agent turn while yielding its token deltas as they arrive.

        Wires the agent's existing ``stream_emitter`` (the same surface the
        WebSocket relay consumes) through the request hot path: a callback pushes
        each answer text chunk onto an :class:`asyncio.Queue`, the turn runs via
        the normal :meth:`_dispatch` (same admission gate + usage snapshot), and
        this generator yields text chunks in real time. On completion it yields a
        final ``("final", (reply, usage))`` marker so the caller has the buffered
        reply (for a no-delta fallback) and the per-turn usage.

        Correctness guarantees baked into the callback:

        * **First token included** — the SDK emits the opening piece as
          ``FIRST_TOKEN`` and only later pieces as ``DELTA_TEXT``; both are
          forwarded so the client never loses the first chunk (Greptile P1).
        * **Reasoning excluded** — deltas flagged ``is_reasoning=True`` are the
          model's private thinking, not the answer, so they are dropped and never
          leaked as answer content to an OpenAI-compatible client (Greptile P1).
        * **Turn isolation** — a per-turn ContextVar token guards the callback so
          concurrent callers sharing one agent never receive each other's text
          (Greptile P1).

        The callback may fire from a worker thread (sync ``chat`` agents), so it
        hands chunks to the loop via ``call_soon_threadsafe``. If the agent has
        no ``stream_emitter``, the turn still completes and only the final marker
        is yielded — the caller then emits today's single buffered chunk.
        """
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        _TEXT_TYPES: tuple = ()
        try:
            from praisonaiagents.streaming.events import StreamEventType as _SET
            _TEXT_TYPES = (_SET.DELTA_TEXT, _SET.FIRST_TOKEN)
        except Exception:
            _SET = None

        # Unique identity for this turn; the callback only forwards events whose
        # running context carries this same token.
        turn_token = object()

        def _on_event(event: Any) -> None:
            if not _TEXT_TYPES:
                return
            if getattr(event, "type", None) not in _TEXT_TYPES:
                return
            # Drop reasoning/thinking deltas — they are not answer content.
            if getattr(event, "is_reasoning", False):
                return
            # Only relay events produced by this turn's execution context.
            if self._stream_turn_var.get() is not turn_token:
                return
            text = getattr(event, "content", None)
            if text:
                loop.call_soon_threadsafe(queue.put_nowait, ("delta", text))

        emitter = getattr(agent, "stream_emitter", None) if _SET is not None else None
        if emitter is not None:
            try:
                emitter.add_callback(_on_event)
            except Exception:
                emitter = None

        async def _run() -> None:
            # Stamp this turn's identity so events emitted during its execution
            # (and only those) pass the callback's isolation check. Native async
            # runs inherit this task's context; ``asyncio.to_thread`` copies it
            # into the worker thread, so the sync ``chat`` path is covered too.
            self._stream_turn_var.set(turn_token)
            try:
                reply, usage = await self._dispatch(session, agent, content)
                await queue.put(("final", (reply, usage)))
            except Exception as exc:  # surface as a terminal marker, never hang
                await queue.put(("error", exc))

        task = asyncio.ensure_future(_run())
        try:
            while True:
                kind, payload = await queue.get()
                if kind == "delta":
                    yield ("delta", payload)
                elif kind == "error":
                    raise payload
                else:  # final
                    yield ("final", payload)
                    break
        finally:
            if emitter is not None:
                try:
                    emitter.remove_callback(_on_event)
                except (ValueError, AttributeError):
                    pass
            if not task.done():
                await task

    @staticmethod
    def _zero_usage() -> dict:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    @staticmethod
    def _usage_for(agent: Any) -> dict:
        """Snapshot the agent's last-turn token metrics as an OpenAI ``usage`` block.

        The core SDK records true per-turn counts on the LLM instance
        (``last_token_metrics`` with ``input_tokens``/``output_tokens``). We read
        them straight off the boundary so cost-accounting clients get real
        figures instead of the previous hardcoded zeros. When metrics are
        unavailable (e.g. a custom agent that does not expose an LLM instance)
        we fall back to zeros so the response stays spec-shaped.

        Call sites MUST invoke this immediately after the dispatched turn
        completes with no intervening ``await`` (see ``_dispatch``); the value
        is read into plain ints here so the returned dict is an immutable
        snapshot that a later concurrent turn cannot mutate.
        """
        zero = GatewayApiEndpoints._zero_usage()
        # Read the already-created LLM instance without forcing lazy creation.
        llm = getattr(agent, "_llm_instance", None) or getattr(
            agent, "llm_instance", None
        )
        metrics = getattr(llm, "last_token_metrics", None) if llm else None
        if metrics is None:
            return zero
        prompt = int(getattr(metrics, "input_tokens", 0) or 0)
        completion = int(getattr(metrics, "output_tokens", 0) or 0)
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        }

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
            opts = body.get("stream_options")
            include_usage = bool(
                isinstance(opts, dict) and opts.get("include_usage")
            )
            return self._sse_chat(
                agent_id, agent, session, content, completion_id, include_usage
            )

        reply, usage = await self._dispatch(session, agent, content)
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
                "usage": usage,
            }
        )

    def _sse_chat(
        self, agent_id, agent, session, content, completion_id, include_usage=False
    ):
        """Emit a spec-shaped SSE chat-completion stream.

        The frames are correctly ``chat.completion.chunk`` shaped and terminate
        with ``[DONE]`` so any OpenAI streaming client parses them.

        When token streaming is enabled (``gateway.api.stream``), the agent's
        existing ``stream_emitter`` is wired through the hot path so each
        ``DELTA_TEXT`` chunk is emitted as its own ``delta.content`` frame in
        real time — genuine time-to-first-token. When streaming is off (the
        default), or the agent produced no token deltas, the content is
        delivered as a single buffered chunk once the turn completes, exactly as
        before; response correctness and client compatibility are unaffected
        either way.

        When the client sets ``stream_options.include_usage`` (the OpenAI
        opt-in for streamed usage), a final ``usage``-only chunk carrying the
        real per-turn token counts is emitted before ``[DONE]``, matching the
        OpenAI streaming contract.
        """
        from starlette.responses import StreamingResponse

        def _content_frame(created, text):
            return {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": agent_id,
                "choices": [
                    {"index": 0, "delta": {"content": text}, "finish_reason": None}
                ],
            }

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

            usage = self._zero_usage()
            if self._streaming_enabled():
                streamed_any = False
                reply = ""
                async for kind, payload in self._dispatch_stream(
                    session, agent, content
                ):
                    if kind == "delta":
                        streamed_any = True
                        yield f"data: {json.dumps(_content_frame(created, payload))}\n\n"
                    else:  # final
                        reply, usage = payload
                # No token deltas seen (agent didn't stream): emit the buffered
                # reply as one chunk so content is never lost. Emitted even for
                # an empty reply so the frame shape matches today's buffered
                # single-chunk path exactly (Greptile P2 — empty replies must
                # still carry a content frame).
                if not streamed_any:
                    yield f"data: {json.dumps(_content_frame(created, reply))}\n\n"
            else:
                reply, usage = await self._dispatch(session, agent, content)
                yield f"data: {json.dumps(_content_frame(created, reply))}\n\n"

            final = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": agent_id,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(final)}\n\n"

            if include_usage:
                usage_chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": agent_id,
                    "choices": [],
                    "usage": usage,
                }
                yield f"data: {json.dumps(usage_chunk)}\n\n"

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
        reply, usage = await self._dispatch(session, agent, content)

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
                "usage": {
                    "input_tokens": usage["prompt_tokens"],
                    "output_tokens": usage["completion_tokens"],
                    "total_tokens": usage["total_tokens"],
                },
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
            reply, _usage = await self._dispatch(session, agent, content)
            return ok(
                {
                    "content": [{"type": "text", "text": reply}],
                    "isError": False,
                }
            )

        return err(-32601, f"Method not found: {method}")
