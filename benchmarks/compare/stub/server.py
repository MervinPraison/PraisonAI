"""OpenAI-compatible stub LLM server (stdlib only).

Every framework talks to this one server through its own real client stack, so
each does the same work with zero network latency and zero cost. The server
records every request so the harness can prove the work was identical.

Replies are ``Final Answer: NONCE-<n> done.`` where ``n`` counts chat replies
since the last ``POST /_reset``. The nonce comes *after* ``Final Answer:``
because ReAct-style parsers (CrewAI) keep only the text after that marker.

Endpoints:
    POST /v1/chat/completions   JSON or SSE (honours stream_options.include_usage)
    POST /v1/responses          minimal, non-streaming
    GET  /v1/models
    GET  /_stats                recorded requests
    POST /_reset                clear recordings and the nonce counter

Usage:
    python server.py [--host 127.0.0.1] [--port 0] [--latency-ms 0]

Prints ``READY <port>`` on stdout once it accepts connections.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STUB_VERSION = "1"
MODEL = "gpt-4o-mini"
USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


def nonce(n: int) -> str:
    # Zero-padded so NONCE-0001 is never a substring of NONCE-0010.
    return f"NONCE-{n:04d}"


def reply_text(n: int) -> str:
    return f"Final Answer: {nonce(n)} done."


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.replies = 0
        self.requests: list[dict] = []

    def snapshot(self) -> dict:
        by_path: dict[str, int] = {}
        for r in self.requests:
            by_path[r["path"]] = by_path.get(r["path"], 0) + 1
        return {
            "stub_version": STUB_VERSION,
            "count_by_path": by_path,
            "bytes_total": sum(r["bytes"] for r in self.requests),
            "requests": list(self.requests),
        }


def _tool_call_args(tool: dict) -> str:
    params = (tool.get("function") or {}).get("parameters") or {}
    props = params.get("properties") or {}
    return json.dumps({k: "x" for k in params.get("required") or list(props)})


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # keep-alive, like a real API
    server: "StubServer"

    def log_message(self, fmt, *args):  # noqa: D401 - silence default logging
        if self.server.log:
            self.server.log.write("%s %s\n" % (self.address_string(), fmt % args))
            self.server.log.flush()

    def setup(self):
        super().setup()
        # Without this, Nagle + delayed ACK stall keep-alive clients ~40 ms/call.
        self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # Headers and body in one write.
        self._headers_buffer.append(b"\r\n" + body)
        self.flush_headers()

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj).encode())

    def _path(self) -> str:
        path = self.path.split("?", 1)[0].rstrip("/")
        # Accept both base_url=".../v1" and base_url="..." styles.
        return path if path.startswith("/v1/") or path.startswith("/_") else "/v1" + path

    def do_GET(self):
        path = self._path()
        if path == "/_stats":
            with self.server.state.lock:
                return self._json(200, self.server.state.snapshot())
        if path == "/v1/models":
            return self._json(200, {"object": "list", "data": [
                {"id": MODEL, "object": "model", "created": 0, "owned_by": "stub"}]})
        self._json(404, {"error": {"message": f"unknown path {path}"}})

    def do_POST(self):
        path = self._path()
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if path == "/_reset":
            with self.server.state.lock:
                self.server.state.reset()
            return self._json(200, {"ok": True})
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            return self._json(400, {"error": {"message": "invalid JSON"}})
        if self.server.latency:
            time.sleep(self.server.latency)
        if path == "/v1/chat/completions":
            return self._chat(raw, body)
        if path == "/v1/responses":
            return self._responses(raw, body)
        self._json(404, {"error": {"message": f"unknown path {path}"}})

    def _record(self, raw: bytes, body: dict, kind: str) -> tuple[int, dict]:
        text = raw.decode("utf-8", "replace")
        state = self.server.state
        with state.lock:
            prev = state.replies
            tools = body.get("tools") or []
            messages = body.get("messages") or []
            wants_tool = bool(tools) and not any(
                isinstance(m, dict) and m.get("role") == "tool" for m in messages)
            if kind == "chat" and not wants_tool:
                state.replies += 1
            entry = {
                "path": self._path(),
                "bytes": len(raw),
                "stream": bool(body.get("stream")),
                "tools": len(tools),
                "keys": sorted(body),
                # The hand-off check: does this request carry the previous reply?
                "has_prev_nonce": (nonce(prev) in text) if prev else None,
                "reply_nonce": nonce(state.replies) if kind == "chat" and not wants_tool else None,
                "tool_call": wants_tool,
            }
            state.requests.append(entry)
            return state.replies, entry

    def _chat(self, raw: bytes, body: dict) -> None:
        n, entry = self._record(raw, body, "chat")
        model = body.get("model") or MODEL
        created = int(time.time())
        cid = f"chatcmpl-stub-{len(self.server.state.requests)}"
        if entry["tool_call"]:
            tool = body["tools"][0]
            message = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "call_stub", "type": "function", "function": {
                    "name": (tool.get("function") or {}).get("name", "tool"),
                    "arguments": _tool_call_args(tool)}}]}
            finish = "tool_calls"
        else:
            message = {"role": "assistant", "content": reply_text(n)}
            finish = "stop"
        if not entry["stream"]:
            return self._json(200, {
                "id": cid, "object": "chat.completion", "created": created, "model": model,
                "choices": [{"index": 0, "message": message, "finish_reason": finish,
                             "logprobs": None}],
                "usage": USAGE})
        base = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model}
        include_usage = bool((body.get("stream_options") or {}).get("include_usage"))
        delta = dict(message)
        if delta.get("tool_calls"):
            delta["tool_calls"] = [dict(delta["tool_calls"][0], index=0)]
        chunks = [
            {**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""},
                                  "finish_reason": None}]},
            {**base, "choices": [{"index": 0, "delta": {k: v for k, v in delta.items()
                                                        if k != "role"},
                                  "finish_reason": None}]},
            {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
        ]
        if include_usage:
            chunks.append({**base, "choices": [], "usage": USAGE})
        sse = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        self._send(200, sse.encode(), "text/event-stream")

    def _responses(self, raw: bytes, body: dict) -> None:
        if body.get("stream"):
            return self._json(400, {"error": {"message": "stub: streaming responses unsupported"}})
        n, _ = self._record(raw, body, "chat")
        self._json(200, {
            "id": f"resp_stub_{n}", "object": "response", "created_at": int(time.time()),
            "model": body.get("model") or MODEL, "status": "completed",
            "output": [{"type": "message", "id": f"msg_stub_{n}", "status": "completed",
                        "role": "assistant", "content": [
                            {"type": "output_text", "text": reply_text(n), "annotations": []}]}],
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
                      "input_tokens_details": {"cached_tokens": 0},
                      "output_tokens_details": {"reasoning_tokens": 0}},
        })


class StubServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, latency_ms: float = 0.0, log=None):
        super().__init__(addr, Handler)
        self.state = State()
        self.latency = latency_ms / 1000.0
        self.log = log


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--latency-ms", type=float, default=0.0)
    p.add_argument("--log", help="append an access log to this file")
    args = p.parse_args(argv)
    log = open(args.log, "a") if args.log else None
    srv = StubServer((args.host, args.port), args.latency_ms, log)
    print(f"READY {srv.server_address[1]}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
