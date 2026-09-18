"""Full Channels + Gateway E2E: Telegram, Slack, gateway preflight/start."""
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
DATA = os.path.join(os.environ.get("APPDATA", ""), "PraisonAI")


def req(port: int, path: str, payload=None, method=None, origin="http://tauri.localhost"):
    data = json.dumps(payload).encode() if payload is not None else None
    m = method or ("POST" if data is not None else "GET")
    headers = {"Content-Type": "application/json"}
    if origin:
        headers["Origin"] = origin
    r = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        method=m,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"error": body}


def wait_log(port: int, target: str, needle: str, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        _, logs = req(port, f"/bots/logs?target={target}")
        text = "\n".join(logs.get("lines") or [])
        if needle.lower() in text.lower():
            return True
        time.sleep(1)
    return False


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
            print("FAIL engine exited")
            proc.wait()
            return 1
        if PORT_MARKER in line:
            port = int(line.split(PORT_MARKER, 1)[1].strip())
            break
    assert port is not None
    print(f"engine :{port}")

    # Clean slate for predictable E2E (keep config dir, reset channels list)
    code, body = req(port, "/bots/channels")
    print("list", code, len(body.get("channels", [])))
    for ch in list(body.get("channels") or []):
        if ch.get("state") == "running":
            req(port, f"/bots/channels/{ch['id']}/stop", method="POST")
        req(port, f"/bots/channels/{ch['id']}", method="DELETE")

    steps = []

    code, tg = req(
        port,
        "/bots/channels",
        {
            "platform": "telegram",
            "name": "E2E Telegram",
            "token_ref": "env:TELEGRAM_BOT_TOKEN",
            "unknown_user_policy": "allow",
        },
    )
    tg_ch = tg.get("channel") or {}
    steps.append(("add telegram", code, tg_ch.get("token_set"), tg_ch.get("id")))
    if not tg_ch.get("token_set"):
        print("FAIL TELEGRAM_BOT_TOKEN missing in engine env")
        proc.terminate()
        return 1

    code, sl = req(
        port,
        "/bots/channels",
        {
            "platform": "slack",
            "name": "E2E Slack",
            "token_ref": "env:SLACK_BOT_TOKEN",
            "app_token_ref": "env:SLACK_APP_TOKEN",
            "unknown_user_policy": "allow",
        },
    )
    sl_ch = sl.get("channel") or {}
    steps.append(("add slack", code, sl_ch.get("token_set"), sl_ch.get("app_token_set")))
    if not sl_ch.get("token_set") or not sl_ch.get("app_token_set"):
        print("FAIL Slack tokens missing in engine env")
        proc.terminate()
        return 1

    code, started = req(port, f"/bots/channels/{tg_ch['id']}/start", method="POST")
    tg_state = (started.get("channel") or started).get("state")
    steps.append(("start telegram", code, tg_state))
    time.sleep(5)
    _, tlogs = req(port, f"/bots/logs?target={tg_ch['id']}")
    tail = (tlogs.get("lines") or [])[-6:]
    print("telegram log tail:")
    for ln in tail:
        print(" ", ln[:120])

    if tg_state != "running":
        print("WARN telegram bot not running:", started.get("error"))
    else:
        req(port, f"/bots/channels/{tg_ch['id']}/stop", method="POST")

    code, gw = req(port, "/bots/gateway/start", {"port": 8765})
    gw_body = gw.get("gateway") or gw
    gw_state = gw_body.get("state")
    steps.append(("start gateway", code, gw_state))
    time.sleep(6)
    _, glogs = req(port, "/bots/logs?target=gateway")
    gtail = (glogs.get("lines") or [])[-12:]
    print("gateway log tail:")
    for ln in gtail:
        print(" ", ln[:120])

    unauthorized = any("unauthorized" in ln.lower() for ln in gtail)
    preflight_fail = any("pre-flight check failed" in ln.lower() for ln in gtail)

    if gw_state == "running":
        req(port, "/bots/gateway/stop", method="POST")
        print("PASS gateway running (telegram + slack)")
    elif unauthorized or preflight_fail:
        print("FAIL gateway preflight — check tokens in ~/.praisonai/.env")
        for name, c, *rest in steps:
            print(f"  {name}: {c} {rest}")
        proc.terminate()
        return 1
    else:
        print("WARN gateway:", gw.get("error"), "state=", gw_state)

    for name, c, *rest in steps:
        print(f"OK {name}: HTTP {c} {rest}")

    proc.terminate()
    proc.wait(timeout=10)
    return 0 if tg_state == "running" or gw_state == "running" else 1


if __name__ == "__main__":
    raise SystemExit(main())
