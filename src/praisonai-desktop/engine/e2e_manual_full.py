"""Manual E2E against real %APPDATA%\\PraisonAI data + ~/.praisonai/.env tokens."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ENGINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")
DATA = os.path.join(os.environ.get("APPDATA", ""), "PraisonAI")
PORT_MARKER = "PRAISONAI_PORT="


def req(port: int, path: str, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    m = method or ("POST" if data is not None else "GET")
    r = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        method=m,
        headers={"Content-Type": "application/json", "Origin": "http://tauri.localhost"},
    )
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"error": body[:300]}


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
    print(f"=== Engine on :{port} (data={DATA}) ===\n")

    steps = []

    code, h = req(port, "/health")
    steps.append(("health", code == 200, h.get("ok")))

    code, ob = req(port, "/onboarding")
    steps.append(("onboarding API", code == 200, f"key={ob.get('api_key_set')} complete={ob.get('complete')}"))

    doc = os.path.join(DATA, "knowledge-test-docs")
    os.makedirs(doc, exist_ok=True)
    marker_path = os.path.join(doc, "e2e-marker.txt")
    with open(marker_path, "w", encoding="utf-8") as f:
        f.write("PraisonAI desktop E2E secret code: NEBULA-7742\n")
    code, kn = req(port, "/knowledge/configure", {"paths": [doc]})
    steps.append(("knowledge configure", code == 200, kn.get("paths")))

    code, kn2 = req(port, "/knowledge/reindex", {})
    ready = kn2.get("ready") if code == 200 else False
    steps.append(("knowledge reindex", code == 200 and ready, kn2.get("error") or "ready"))

    if ready:
        code, q = req(port, "/knowledge/query", {"query": "What is the secret code?"})
        ctx = (q.get("context") or "").lower()
        steps.append(("knowledge query", code == 200 and "nebula" in ctx, ctx[:80] or q.get("error")))

    code, chlist = req(port, "/bots/channels")
    channels = chlist.get("channels") or []
    steps.append(("list channels", code == 200, len(channels)))

    tg = next((c for c in channels if c.get("platform") == "telegram"), None)
    sl = next((c for c in channels if c.get("platform") == "slack"), None)
    if not tg:
        code, r = req(
            port,
            "/bots/channels",
            {
                "platform": "telegram",
                "name": "E2E TG",
                "token_ref": "env:TELEGRAM_BOT_TOKEN",
                "unknown_user_policy": "allow",
            },
        )
        tg = (r.get("channel") or r) if code in (200, 201) else None
    if not sl:
        code, r = req(
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
        sl = (r.get("channel") or r) if code in (200, 201) else None

    for ch in channels:
        if ch.get("state") == "running":
            req(port, f"/bots/channels/{ch['id']}/stop", {})

    code, gw = req(port, "/bots/gateway/start", {"port": 8765})
    gw_state = (gw.get("gateway") or gw).get("state")
    steps.append(("gateway start", code == 200 and gw_state == "running", gw_state or gw.get("error")))

    time.sleep(8)
    code, logs = req(port, "/bots/logs?target=gateway")
    tail = "\n".join((logs.get("lines") or [])[-25:]).lower()
    tg_ok = "telegram" in tail and ("started" in tail or "initialized" in tail)
    sl_ok = "slack" in tail and ("started" in tail or "initialized" in tail)
    deny = "silently dropped" in tail and "telegram" in tail
    steps.append(("gateway telegram logs", tg_ok and not deny, "see gateway.log"))
    steps.append(("gateway slack logs", sl_ok, "see gateway.log"))

    if gw_state == "running":
        req(port, "/bots/gateway/stop", {})

    code, test = req(port, "/onboarding/test", {"prompt": "Say hi in one short sentence."})
    reply = (test.get("reply") or "")[:100]
    steps.append(("chat test Hi", code == 200 and bool(reply), reply or test.get("error")))

    print("Results:")
    all_ok = True
    for name, ok, detail in steps:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"  [{mark}] {name}: {detail}")

    proc.terminate()
    print("\n" + ("ALL PASS" if all_ok else "SOME FAILURES — open Desktop and retry GUI"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
