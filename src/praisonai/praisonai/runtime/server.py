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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional

from .descriptor import RuntimeDescriptor


class WarmRuntime:
    """Holds warm agent state and executes prompts for the runtime server."""

    def __init__(self, model: Optional[str] = None):
        self._default_model = model
        self._agents: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._agent_locks: Dict[str, threading.Lock] = {}
        self.last_activity = time.time()

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

    def run(self, prompt: str, model: Optional[str] = None) -> str:
        """Execute a prompt against the warm agent and return the result text.

        Access to each cached Agent is serialized via a per-model lock because
        the ThreadingHTTPServer dispatches requests on parallel threads and a
        single ``Agent`` instance is not safe for concurrent ``start`` calls.
        """
        self.last_activity = time.time()
        key = self._agent_key(model)
        with self._lock_for(key):
            agent = self._get_agent(key)
            result = agent.start(prompt)
        self.last_activity = time.time()
        return str(result) if result is not None else ""


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
                self._send_json(200, {"ok": True})
                return

            if self.path == "/run":
                payload = self._read_json()
                prompt = payload.get("prompt")
                if not prompt:
                    self._send_json(400, {"ok": False, "error": "missing prompt"})
                    return
                try:
                    result = runtime.run(prompt, model=payload.get("model"))
                    self._send_json(200, {"ok": True, "result": result})
                except Exception as e:  # noqa: BLE001 - surface to client as error
                    self._send_json(200, {"ok": False, "error": str(e)})
                return

            self._send_json(404, {"ok": False, "error": "not found"})

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
