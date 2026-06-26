"""
Warm local runtime server.

A long-lived loopback HTTP process that keeps provider clients (and, through the
agent, any configured MCP connections) warm across ``praisonai run`` invocations.
It holds one warm :class:`~praisonaiagents.Agent` per model and reuses it, so the
second and subsequent runs skip per-invocation cold-start.

Built only on the standard library (``http.server``) to keep the dependency
surface and import cost minimal. Local-first security: binds loopback, requires a
per-process bearer token, and auto-shuts down after an idle timeout.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
import queue
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlsplit

from .descriptor import RuntimeDescriptor, get_runtime_version


class SessionEventHub:
    """Fan out per-session events to all attached clients.

    Each ``/run`` carries an optional ``session_id``. While a prompt executes,
    the runtime publishes structured events (start, result, error) tagged with
    that session id; any number of ``attach`` clients subscribed to the same id
    receive them in real time via Server-Sent Events. This is the building block
    that lets a second terminal observe a live session.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # session_id -> list of subscriber queues
        self._subscribers: Dict[str, List["queue.Queue[Optional[Dict[str, Any]]]"]] = {}

    def subscribe(self, session_id: str) -> "queue.Queue[Optional[Dict[str, Any]]]":
        """Register a subscriber for ``session_id`` and return its queue."""
        q: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue()
        with self._lock:
            self._subscribers.setdefault(session_id, []).append(q)
        return q

    def unsubscribe(self, session_id: str, q: "queue.Queue[Optional[Dict[str, Any]]]") -> None:
        """Remove a subscriber queue for ``session_id`` (idempotent)."""
        with self._lock:
            subs = self._subscribers.get(session_id)
            if not subs:
                return
            try:
                subs.remove(q)
            except ValueError:
                pass
            if not subs:
                self._subscribers.pop(session_id, None)

    def publish(self, session_id: str, event: Dict[str, Any]) -> None:
        """Publish ``event`` to every subscriber of ``session_id``."""
        if not session_id:
            return
        with self._lock:
            subs = list(self._subscribers.get(session_id, ()))
        for q in subs:
            q.put(event)

    def has_subscribers(self, session_id: str) -> bool:
        with self._lock:
            return bool(self._subscribers.get(session_id))


class WarmRuntime:
    """Holds warm agent state and executes prompts for the runtime server."""

    def __init__(self, model: Optional[str] = None, hub: Optional[SessionEventHub] = None):
        self._default_model = model
        self._agents: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._agent_locks: Dict[str, threading.Lock] = {}
        self.last_activity = time.time()
        # Event hub used to fan out live session events to attached clients.
        self.hub = hub or SessionEventHub()

    def _agent_key(self, model: Optional[str]) -> str:
        return model or self._default_model or "__default__"

    def _get_agent(self, key: str):
        """Return a warm Agent for ``key``, creating it once and reusing it."""
        with self._lock:
            agent = self._agents.get(key)
            if agent is None:
                from praisonaiagents import Agent

                config: Dict[str, Any] = {
                    "name": "RuntimeAgent",
                    "role": "Assistant",
                    "goal": "Complete the task",
                }
                resolved = None if key == "__default__" else key
                resolved = resolved or self._default_model
                if resolved:
                    config["llm"] = resolved
                agent = Agent(**config)
                self._agents[key] = agent
            return agent

    def _lock_for(self, key: str) -> threading.Lock:
        """Return a per-agent lock so concurrent /run calls serialize per model."""
        with self._lock:
            lock = self._agent_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._agent_locks[key] = lock
            return lock

    def _evict_agent(self, key: str) -> None:
        """Drop the cached agent for ``key`` so the next call gets a fresh one."""
        with self._lock:
            self._agents.pop(key, None)

    def run(
        self,
        prompt: str,
        model: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """Execute a prompt against the warm agent and return the result text.

        Access to each cached Agent is serialized via a per-model lock because
        the ThreadingHTTPServer dispatches requests on parallel threads and a
        single ``Agent`` instance is not safe for concurrent ``start`` calls.

        If ``agent.start`` raises (LLM error, timeout, etc.) the agent may be
        left with partial conversation state (e.g. an unmatched user turn), so
        it is evicted from the cache and the next call rebuilds a clean agent.

        When ``session_id`` is given, live events (start/result/error) are
        published to the hub so attached clients can observe the session in real
        time.
        """
        self.last_activity = time.time()
        key = self._agent_key(model)
        if session_id:
            self.hub.publish(session_id, {
                "type": "run.start",
                "session_id": session_id,
                "prompt": prompt,
            })
        with self._lock_for(key):
            agent = self._get_agent(key)
            try:
                result = agent.start(prompt)
            except Exception as e:
                self._evict_agent(key)
                if session_id:
                    self.hub.publish(session_id, {
                        "type": "run.error",
                        "session_id": session_id,
                        "error": str(e),
                    })
                raise
        self.last_activity = time.time()
        text = str(result) if result is not None else ""
        if session_id:
            self.hub.publish(session_id, {
                "type": "run.result",
                "session_id": session_id,
                "ok": True,
                "result": text,
            })
        return text


def _make_handler(token: str, runtime: WarmRuntime):
    """Build a request handler bound to the runtime's token and state."""

    class _Handler(BaseHTTPRequestHandler):
        # Silence default stderr request logging to keep the daemon quiet.
        def log_message(self, *args: Any) -> None:  # noqa: D401
            return

        def _authorized(self) -> bool:
            header = self.headers.get("Authorization", "")
            expected = f"Bearer {token}"
            return secrets.compare_digest(header, expected)

        def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> Dict[str, Any]:
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8")) if raw else {}
            except ValueError:
                return {}

        def do_POST(self) -> None:  # noqa: N802
            if not self._authorized():
                self._send_json(401, {"ok": False, "error": "unauthorized"})
                return

            if self.path == "/healthz":
                # Advertise the runtime version so clients can run the
                # version-compat handshake over the wire as well as via the
                # lockfile descriptor.
                self._send_json(200, {"ok": True, "version": get_runtime_version()})
                return

            if self.path == "/run":
                payload = self._read_json()
                prompt = payload.get("prompt")
                if not prompt:
                    self._send_json(400, {"ok": False, "error": "missing prompt"})
                    return
                try:
                    result = runtime.run(
                        prompt,
                        model=payload.get("model"),
                        session_id=payload.get("session_id"),
                    )
                    self._send_json(200, {"ok": True, "result": result})
                except Exception as e:  # noqa: BLE001 - surface to client as error
                    self._send_json(200, {"ok": False, "error": str(e)})
                return

            self._send_json(404, {"ok": False, "error": "not found"})

        def do_GET(self) -> None:  # noqa: N802
            if not self._authorized():
                self._send_json(401, {"ok": False, "error": "unauthorized"})
                return

            # Live session event stream: /sessions/{id}/events (Server-Sent
            # Events). An attached client opens this and receives each event the
            # runtime publishes for that session until it disconnects.
            # Strip any query string before matching the path, then percent-
            # decode the session id so it round-trips with the client's
            # ``quote(session_id, safe="")`` encoding.
            path = urlsplit(self.path).path
            prefix, suffix = "/sessions/", "/events"
            if path.startswith(prefix) and path.endswith(suffix):
                session_id = unquote(path[len(prefix):-len(suffix)])
                if not session_id:
                    self._send_json(400, {"ok": False, "error": "missing session id"})
                    return
                self._stream_session_events(session_id)
                return

            self._send_json(404, {"ok": False, "error": "not found"})

        def _stream_session_events(self, session_id: str) -> None:
            """Stream session events as SSE until the client disconnects."""
            q = runtime.hub.subscribe(session_id)
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                # Initial comment so the client knows the stream is live.
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()
                while True:
                    try:
                        event = q.get(timeout=15.0)
                    except queue.Empty:
                        # Heartbeat keeps idle connections (and proxies) alive.
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
                        continue
                    if event is None:
                        break
                    line = "data: " + json.dumps(event) + "\n\n"
                    self.wfile.write(line.encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                # Client disconnected; fall through to cleanup.
                pass
            finally:
                runtime.hub.unsubscribe(session_id, q)

    return _Handler


def serve_runtime(
    host: str = "127.0.0.1",
    port: int = 0,
    model: Optional[str] = None,
    idle_timeout: float = 1800.0,
    project_path: Optional[str] = None,
) -> None:
    """Start the warm runtime, write the lockfile, and serve until stopped.

    Args:
        host: Loopback host to bind (defaults to ``127.0.0.1``).
        port: Port to bind; ``0`` auto-selects a free port.
        model: Default model for warm agents.
        idle_timeout: Seconds of inactivity before auto-shutdown (``0`` disables).
        project_path: Project root for the lockfile location.
    """
    runtime = WarmRuntime(model=model)
    token = secrets.token_urlsafe(32)
    handler = _make_handler(token, runtime)

    httpd = ThreadingHTTPServer((host, port), handler)
    bound_host, bound_port = httpd.server_address[0], httpd.server_address[1]

    descriptor = RuntimeDescriptor(
        host=str(bound_host),
        port=int(bound_port),
        token=token,
        pid=os.getpid(),
        version=get_runtime_version(),
    )
    descriptor.write(project_path)

    # Background idle-shutdown watcher: stop the server when inactive too long.
    stop_event = threading.Event()

    def _idle_watch() -> None:
        if idle_timeout and idle_timeout > 0:
            while not stop_event.wait(timeout=min(idle_timeout, 30.0)):
                if time.time() - runtime.last_activity > idle_timeout:
                    httpd.shutdown()
                    return

    watcher = threading.Thread(target=_idle_watch, daemon=True)
    watcher.start()

    try:
        httpd.serve_forever()
    finally:
        stop_event.set()
        httpd.server_close()
        RuntimeDescriptor.remove(project_path)
