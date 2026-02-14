"""
launchd service management for PraisonAI bots (macOS).

Generates and manages a launchd plist for always-on bots.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from typing import Any, Dict

logger = logging.getLogger(__name__)

LABEL = "ai.praison.bot"
PLIST_NAME = f"{LABEL}.plist"


def _launch_agents_dir() -> str:
    return os.path.expanduser("~/Library/LaunchAgents")


def _plist_path() -> str:
    return os.path.join(_launch_agents_dir(), PLIST_NAME)


def _log_dir() -> str:
    d = os.path.expanduser("~/.praisonai/logs")
    os.makedirs(d, exist_ok=True)
    return d


def _generate_plist(config_path: str) -> str:
    """Generate a launchd plist XML for the bot."""
    python = shutil.which("python3") or shutil.which("python") or sys.executable
    abs_config = os.path.abspath(config_path)
    working_dir = os.path.dirname(abs_config) or os.getcwd()
    log_dir = _log_dir()

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>-m</string>
        <string>praisonai</string>
        <string>bot</string>
        <string>start</string>
        <string>--config</string>
        <string>{abs_config}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{working_dir}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_dir}/bot-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/bot-stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{os.environ.get('PATH', '/usr/bin:/usr/local/bin')}</string>
    </dict>
</dict>
</plist>
"""


def install(config_path: str = "bot.yaml", **kwargs: Any) -> Dict[str, Any]:
    """Install the launchd agent."""
    la_dir = _launch_agents_dir()
    os.makedirs(la_dir, exist_ok=True)

    plist_content = _generate_plist(config_path)
    plist_path = _plist_path()

    with open(plist_path, "w") as f:
        f.write(plist_content)

    try:
        subprocess.run(["launchctl", "load", plist_path], check=True, capture_output=True)
        return {"ok": True, "plist_path": plist_path, "message": f"Service installed and loaded: {plist_path}"}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "error": f"launchctl error: {e.stderr.decode()[:300] if e.stderr else str(e)}"}


def uninstall() -> Dict[str, Any]:
    """Unload and remove the launchd agent."""
    plist_path = _plist_path()
    try:
        subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
        if os.path.exists(plist_path):
            os.remove(plist_path)
        return {"ok": True, "message": "Service removed"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_status() -> Dict[str, Any]:
    """Get the status of the launchd agent."""
    plist_path = _plist_path()
    installed = os.path.exists(plist_path)

    if not installed:
        return {"installed": False, "running": False, "platform": "launchd"}

    try:
        result = subprocess.run(
            ["launchctl", "list", LABEL],
            capture_output=True, text=True,
        )
        running = result.returncode == 0
        return {"installed": True, "running": running, "platform": "launchd", "plist_path": plist_path}
    except Exception:
        return {"installed": True, "running": False, "platform": "launchd", "plist_path": plist_path}


def get_logs(lines: int = 50) -> str:
    """Get recent logs from the service."""
    log_path = os.path.join(_log_dir(), "bot-stderr.log")
    if not os.path.exists(log_path):
        return "No log file found."
    try:
        with open(log_path) as f:
            all_lines = f.readlines()
            return "".join(all_lines[-lines:])
    except Exception as e:
        return f"Error reading logs: {e}"
