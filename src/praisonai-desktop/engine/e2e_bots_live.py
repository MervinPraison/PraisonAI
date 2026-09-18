"""End-to-end smoke test for Desktop Channels/Gateway API (local engine)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ENGINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")
PORT_MARKER = "PRAISONAI_PORT="
DATA = os.environ.get(
    "PRAISONAI_DESKTOP_HOME",
    os.path.join(os.environ.get("APPDATA", ""), "PraisonAI"),
)


def req(port: int, path: str, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    m = method or ("POST" if data else "GET")
    r = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        method=m,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=30) as resp:
        return resp.status, json.loads(resp.read().decode())


def main() -> int:
    env = dict(os.environ, PRAISONAI_DESKTOP_HOME=DATA)
    proc = subprocess.Popen(
        [sys.executable, "-u", ENGINE],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    port = None
    deadline = time.time() + 90
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            print("engine exited early")
            proc.wait()
            return 1
        if PORT_MARKER in line:
            port = int(line.split(PORT_MARKER, 1)[1].strip())
            break
    if port is None:
        print("no port announced")
        proc.terminate()
        return 1

    print(f"engine on :{port} data={DATA}")
    code, body = req(port, "/bots/channels")
    print("GET /bots/channels", code, "count=", len(body.get("channels", [])))

    code, gw = req(port, "/bots/gateway")
    print("GET /bots/gateway", code, gw.get("state"), "channels=", gw.get("channels_configured"))

    channels = body.get("channels") or []
    tg = next((c for c in channels if c.get("platform") == "telegram"), None)
    if not tg:
        code, added = req(
            port,
            "/bots/channels",
            {
                "platform": "telegram",
                "name": "E2E Telegram",
                "token_ref": "env:TELEGRAM_BOT_TOKEN",
            },
        )
        print("POST /bots/channels", code, added.get("channel", {}).get("id"))
        tg = added.get("channel")

    if tg and tg.get("token_set"):
        cid = tg["id"]
        try:
            code, started = req(port, f"/bots/channels/{cid}/start", method="POST")
            print("POST start", code, started.get("channel", started).get("state"))
            time.sleep(4)
            code, logs = req(port, f"/bots/logs?target={cid}")
            tail = logs.get("lines") or []
            print("log tail (last 8 lines):")
            for ln in tail[-8:]:
                print(" ", ln)
            req(port, f"/bots/channels/{cid}/stop", method="POST")
            print("stopped channel", cid)
        except urllib.error.HTTPError as exc:
            err = json.loads(exc.read().decode())
            print("start failed:", err)
    else:
        print("TELEGRAM_BOT_TOKEN not set in ~/.praisonai/.env — skipping live bot start")

    proc.terminate()
    proc.wait(timeout=10)
    print("E2E OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
