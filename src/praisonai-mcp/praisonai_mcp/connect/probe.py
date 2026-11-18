"""Check a configured server for real, and remember which clients connect.

:func:`verify` runs the MCP handshake the editor will run (``initialize``,
``notifications/initialized``, ``tools/list``) against the exact command or
URL that was written, and returns the tool count.

:func:`record` is called by the server on every ``initialize``: it keeps the
client's name, version, first seen and last active in
``<praisonai mcp dir>/connections.json``. :func:`connections` reads it back
for ``praisonai connect`` and PraisonAIUI. Local and private: nothing leaves
the machine.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .catalog import ServerSpec

PROBE_CLIENT = "praisonai-connect"
PROTOCOL = "2025-06-18"


@dataclass
class ProbeResult:
    ok: bool
    tools: int = 0
    server: str = ""
    error: str = ""


def _init_msg() -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": PROTOCOL, "capabilities": {},
                   "clientInfo": {"name": PROBE_CLIENT, "version": "1"}},
    }


def verify(spec: ServerSpec, timeout: float = 30.0) -> ProbeResult:
    """Handshake with the server ``spec`` describes; never raises."""
    try:
        return _verify_url(spec, timeout) if spec.url else _verify_stdio(spec, timeout)
    except Exception as exc:  # report, do not crash the CLI
        return ProbeResult(False, error=str(exc) or type(exc).__name__)


def _verify_stdio(spec: ServerSpec, timeout: float) -> ProbeResult:
    errlog = tempfile.TemporaryFile()
    proc = subprocess.Popen(
        spec.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errlog,
        env={**os.environ, "PRAISONAI_MCP_PROBE": "1"},
    )
    lines: "queue.Queue[Optional[bytes]]" = queue.Queue()

    def pump() -> None:
        for raw in proc.stdout:  # type: ignore[union-attr]
            lines.put(raw)
        lines.put(None)

    threading.Thread(target=pump, daemon=True).start()
    deadline = time.monotonic() + timeout

    def send(msg: Dict[str, Any]) -> None:
        proc.stdin.write((json.dumps(msg) + "\n").encode())  # type: ignore[union-attr]
        proc.stdin.flush()  # type: ignore[union-attr]

    def reply(msg_id: int) -> Dict[str, Any]:
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError(f"no answer in {timeout:.0f}s")
            raw = lines.get(timeout=left)
            if raw is None:
                errlog.seek(0)
                tail = errlog.read().decode("utf-8", "replace").strip().splitlines()[-1:]
                raise RuntimeError("the server exited before answering" + (f": {tail[0]}" if tail else ""))
            try:
                msg = json.loads(raw)
            except ValueError:
                continue  # a stray print on stdout
            if msg.get("id") == msg_id:
                if "error" in msg:
                    raise RuntimeError(msg["error"].get("message", "error"))
                return msg.get("result") or {}

    try:
        send(_init_msg())
        info = reply(1).get("serverInfo", {})
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        count, cursor, msg_id = 0, None, 2
        while True:
            send({"jsonrpc": "2.0", "id": msg_id, "method": "tools/list",
                  "params": {"cursor": cursor} if cursor else {}})
            page = reply(msg_id)
            count += len(page.get("tools", []))
            cursor = page.get("nextCursor")
            msg_id += 1
            if not cursor:
                break
        return ProbeResult(True, count, info.get("name", ""))
    finally:
        proc.kill()
        proc.wait(timeout=5)
        errlog.close()


def _verify_url(spec: ServerSpec, timeout: float) -> ProbeResult:
    session: Dict[str, str] = {}

    def post(msg: Dict[str, Any]) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": PROTOCOL, **session}
        req = urllib.request.Request(spec.url, data=json.dumps(msg).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - user-given URL
            if resp.headers.get("Mcp-Session-Id"):
                session["Mcp-Session-Id"] = resp.headers["Mcp-Session-Id"]
            body = resp.read().decode("utf-8", "replace")
        if "id" not in msg:
            return {}
        for chunk in [body] + [ln[5:] for ln in body.splitlines() if ln.startswith("data:")]:
            try:
                data = json.loads(chunk)
            except ValueError:
                continue
            if isinstance(data, dict) and data.get("id") == msg["id"]:
                if "error" in data:
                    raise RuntimeError(data["error"].get("message", "error"))
                return data.get("result") or {}
        raise RuntimeError("no JSON-RPC answer in the response")

    info = post(_init_msg()).get("serverInfo", {})
    post({"jsonrpc": "2.0", "method": "notifications/initialized"})
    tools = post({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}).get("tools", [])
    return ProbeResult(True, len(tools), info.get("name", ""))


# --------------------------------------------------------------------------- ledger


def ledger_path() -> Path:
    from praisonaiagents.paths import get_mcp_dir

    return get_mcp_dir() / "connections.json"


def connections(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Clients seen by the server, most recent first."""
    try:
        data = json.loads((path or ledger_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = [r for r in data.values() if isinstance(r, dict)] if isinstance(data, dict) else []
    return sorted(rows, key=lambda r: r.get("last_active", 0), reverse=True)


_lock = threading.Lock()


def record(client_info: Optional[Dict[str, Any]], transport: str = "stdio",
           path: Optional[Path] = None, now: Optional[float] = None) -> None:
    """Note that ``client_info`` connected. Best effort: never raises."""
    if not isinstance(client_info, dict) or os.environ.get("PRAISONAI_MCP_PROBE"):
        return
    name = str(client_info.get("name") or "").strip()[:80]
    if not name or name == PROBE_CLIENT:
        return
    try:
        path = path or ledger_path()
        stamp = now if now is not None else time.time()
        with _lock:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    data = {}
            except (OSError, ValueError):
                data = {}
            row = data.get(name) or {"name": name, "first_seen": stamp, "sessions": 0}
            row.update(version=str(client_info.get("version") or "")[:40], last_active=stamp,
                       transport=transport, sessions=int(row.get("sessions", 0)) + 1)
            data[name] = row
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            os.replace(tmp, path)
    except Exception:  # the ledger must never break a handshake
        pass
