"""E2E: onboarding, knowledge API, discord channel add (engine only)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

ENGINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")
PORT_MARKER = "PRAISONAI_PORT="


def req(port: int, path: str, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    m = method or ("POST" if data is not None else "GET")
    r = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        method=m,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=60) as resp:
        body = resp.read().decode()
        return resp.status, json.loads(body) if body else {}


def main() -> int:
    data = os.path.join(tempfile.gettempdir(), "praison-desktop-e2e")
    os.makedirs(data, exist_ok=True)
    env = dict(os.environ, PRAISONAI_DESKTOP_HOME=data)
    proc = subprocess.Popen(
        [sys.executable, "-u", ENGINE],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    port = None
    deadline = __import__("time").time() + 90
    while __import__("time").time() < deadline:
        line = proc.stdout.readline()
        if not line:
            proc.wait()
            print("FAIL engine exited")
            return 1
        if PORT_MARKER in line:
            port = int(line.split(PORT_MARKER, 1)[1].strip())
            break
    assert port is not None
    print(f"engine :{port}")

    code, ob = req(port, "/onboarding")
    print("onboarding", code, ob.get("api_key_set"), ob.get("complete"))

    doc = os.path.join(data, "docs")
    os.makedirs(doc, exist_ok=True)
    with open(os.path.join(doc, "note.txt"), "w", encoding="utf-8") as f:
        f.write("Desktop E2E marker ZEBRA-9917")
    code, cfg = req(port, "/knowledge/configure", {"paths": [doc]})
    print("knowledge configure", code, cfg.get("paths"))

    if os.environ.get("OPENAI_API_KEY"):
        try:
            code, idx = req(port, "/knowledge/reindex", {})
            print("knowledge reindex", code, idx.get("ready"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode()
            print("knowledge reindex skipped", exc.code, body[:200])
    else:
        print("knowledge reindex skipped (no OPENAI_API_KEY)")

    code, ch = req(
        port,
        "/bots/channels",
        {"platform": "discord", "name": "E2E Discord", "unknown_user_policy": "allow"},
    )
    print("add discord", code, (ch.get("channel") or {}).get("platform"))

    proc.terminate()
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
