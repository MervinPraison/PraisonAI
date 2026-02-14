"""
systemd service management for PraisonAI bots (Linux).

Generates and manages a systemd user service unit file.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from typing import Any, Dict

logger = logging.getLogger(__name__)

SERVICE_NAME = "praisonai-bot"
UNIT_FILE_NAME = f"{SERVICE_NAME}.service"


def _user_unit_dir() -> str:
    """Get the systemd user unit directory."""
    return os.path.expanduser("~/.config/systemd/user")


def _unit_path() -> str:
    return os.path.join(_user_unit_dir(), UNIT_FILE_NAME)


def _generate_unit(config_path: str) -> str:
    """Generate a systemd unit file for the bot."""
    python = shutil.which("python3") or shutil.which("python") or sys.executable
    abs_config = os.path.abspath(config_path)
    working_dir = os.path.dirname(abs_config) or os.getcwd()

    return f"""[Unit]
Description=PraisonAI Bot Service
After=network.target

[Service]
Type=simple
WorkingDirectory={working_dir}
ExecStart={python} -m praisonai bot start --config {abs_config}
Restart=always
RestartSec=5
Environment=PATH={os.environ.get('PATH', '/usr/bin')}

[Install]
WantedBy=default.target
"""


def install(config_path: str = "bot.yaml", **kwargs: Any) -> Dict[str, Any]:
    """Install the systemd user service."""
    unit_dir = _user_unit_dir()
    os.makedirs(unit_dir, exist_ok=True)

    unit_content = _generate_unit(config_path)
    unit_path = _unit_path()

    with open(unit_path, "w") as f:
        f.write(unit_content)

    # Reload systemd and enable the service
    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, capture_output=True)
        subprocess.run(["systemctl", "--user", "enable", SERVICE_NAME], check=True, capture_output=True)
        subprocess.run(["systemctl", "--user", "start", SERVICE_NAME], check=True, capture_output=True)
        # Enable lingering so the service runs without login
        user = os.environ.get("USER", "")
        if user:
            subprocess.run(["loginctl", "enable-linger", user], capture_output=True)
        return {"ok": True, "unit_path": unit_path, "message": f"Service installed and started: {unit_path}"}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "error": f"systemctl error: {e.stderr.decode()[:300] if e.stderr else str(e)}"}
    except FileNotFoundError:
        return {"ok": False, "error": "systemctl not found. Is systemd available?"}


def uninstall() -> Dict[str, Any]:
    """Stop and remove the systemd user service."""
    unit_path = _unit_path()
    try:
        subprocess.run(["systemctl", "--user", "stop", SERVICE_NAME], capture_output=True)
        subprocess.run(["systemctl", "--user", "disable", SERVICE_NAME], capture_output=True)
        if os.path.exists(unit_path):
            os.remove(unit_path)
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
        return {"ok": True, "message": "Service removed"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_status() -> Dict[str, Any]:
    """Get the status of the systemd service."""
    unit_path = _unit_path()
    installed = os.path.exists(unit_path)

    if not installed:
        return {"installed": False, "running": False, "platform": "systemd"}

    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", SERVICE_NAME],
            capture_output=True, text=True,
        )
        running = result.stdout.strip() == "active"
        return {"installed": True, "running": running, "platform": "systemd", "unit_path": unit_path}
    except Exception:
        return {"installed": True, "running": False, "platform": "systemd", "unit_path": unit_path}


def get_logs(lines: int = 50) -> str:
    """Get recent logs from the service."""
    try:
        result = subprocess.run(
            ["journalctl", "--user", "-u", SERVICE_NAME, "-n", str(lines), "--no-pager"],
            capture_output=True, text=True,
        )
        return result.stdout
    except Exception as e:
        return f"Error fetching logs: {e}"
