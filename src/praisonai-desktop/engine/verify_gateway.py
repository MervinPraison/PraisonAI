"""Verify token + gateway start after upgrade."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

import bots

HOME = Path(os.environ["APPDATA"]) / "PraisonAI"
dotenv = Path.home() / ".praisonai" / ".env"
bots.load_dotenv_file(dotenv)
token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
if not token:
    print("FAIL no TELEGRAM_BOT_TOKEN")
    raise SystemExit(1)
with urllib.request.urlopen(
    f"https://api.telegram.org/bot{token}/getMe", timeout=15
) as r:
    data = json.loads(r.read())
print("getMe", data.get("ok"), (data.get("result") or {}).get("username"))

sup = bots.BotSupervisor(HOME, sys.executable)
for ch in sup.list_channels():
    try:
        sup.stop_channel(ch["id"])
    except Exception:
        pass
sup.stop_gateway()
status = sup.start_gateway(8765)
print("gateway", status.get("state"))
time.sleep(4)
tail = sup.logs("gateway").get("lines", [])[-6:]
for ln in tail:
    if "Unauthorized" in ln or "Pre-flight" in ln or "listening" in ln.lower():
        print("LOG", ln[:120])
sup.stop_gateway()
print("DONE")
