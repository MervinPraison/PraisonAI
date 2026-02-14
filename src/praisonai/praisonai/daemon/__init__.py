"""
Daemon service management for PraisonAI bots.

Provides OS-level service install/uninstall/status for always-on bots.
Supports systemd (Linux) and launchd (macOS).
"""

from __future__ import annotations

import platform
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _detect_platform() -> str:
    """Detect the current OS platform."""
    system = platform.system().lower()
    if system == "linux":
        return "systemd"
    elif system == "darwin":
        return "launchd"
    elif system == "windows":
        return "windows"
    return "unknown"


def get_daemon_status() -> Dict[str, Any]:
    """Get daemon status for the current platform."""
    plat = _detect_platform()
    if plat == "systemd":
        from .systemd import get_status
        return get_status()
    elif plat == "launchd":
        from .launchd import get_status
        return get_status()
    return {"installed": False, "running": False, "platform": plat, "error": "Unsupported platform"}


def install_daemon(config_path: str = "bot.yaml", **kwargs: Any) -> Dict[str, Any]:
    """Install the bot as an OS daemon service."""
    plat = _detect_platform()
    if plat == "systemd":
        from .systemd import install
        return install(config_path=config_path, **kwargs)
    elif plat == "launchd":
        from .launchd import install
        return install(config_path=config_path, **kwargs)
    return {"ok": False, "error": f"Unsupported platform: {plat}"}


def uninstall_daemon() -> Dict[str, Any]:
    """Uninstall the bot daemon service."""
    plat = _detect_platform()
    if plat == "systemd":
        from .systemd import uninstall
        return uninstall()
    elif plat == "launchd":
        from .launchd import uninstall
        return uninstall()
    return {"ok": False, "error": f"Unsupported platform: {plat}"}
