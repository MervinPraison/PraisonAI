"""
Daemon service management for PraisonAI bots.

Provides OS-level service install/uninstall/status for always-on bots.
Supports systemd (Linux) and launchd (macOS).
"""

from __future__ import annotations

import platform
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Held back beyond the gateway's own shutdown budget so its self-exit watchdog
# fires before the supervisor's SIGKILL (Issue #5815).
_SUPERVISOR_EXIT_MARGIN_S = 10.0
# Floor matching the gateway's default shutdown grace (LoopWatchdogPolicy).
_DEFAULT_SHUTDOWN_GRACE_S = 5.0


def stop_timeout_seconds(config_path: str) -> int:
    """Stop deadline (seconds) the service manager should allow the gateway.

    Sized from the same drain budget the gateway will use on shutdown — a
    channel drain and a session drain, each bounded by ``drain_timeout``, plus
    the shutdown grace and an exit margin — so ``systemctl restart`` / a
    redeploy never SIGKILLs the process mid-drain (Issue #5815). Unreadable
    config falls back to the production drain window.
    """
    import math

    from ..bots._reliability import _PRODUCTION_DRAIN_SECONDS, resolve_reliability

    gw: Dict[str, Any] = {}
    try:
        import yaml

        with open(config_path, "r", encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
        if isinstance(doc, dict) and isinstance(doc.get("gateway"), dict):
            gw = doc["gateway"]
    except Exception:  # advisory — never block install on config parse
        pass

    def _num(value: Any, default: Optional[float]) -> Optional[float]:
        try:
            value = float(value)
        except (TypeError, ValueError):
            return default
        return value if math.isfinite(value) and value >= 0 else default

    try:
        drain = resolve_reliability(
            gw.get("reliability"),
            # A supervised daemon is a deployment; treat an unset host as one.
            bind_host=gw.get("host") or "0.0.0.0",
            drain_timeout=_num(gw.get("drain_timeout"), None),
        ).drain_timeout or 0.0
    except ValueError:  # bad preset name — the gateway will refuse to start
        drain = _PRODUCTION_DRAIN_SECONDS
    watchdog = gw.get("watchdog") if isinstance(gw.get("watchdog"), dict) else {}
    grace = _num(watchdog.get("shutdown_grace"), _DEFAULT_SHUTDOWN_GRACE_S)
    return int(math.ceil(2 * drain + grace + _SUPERVISOR_EXIT_MARGIN_S))


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
    elif plat == "windows":
        from .windows import get_status
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
    elif plat == "windows":
        from .windows import install
        return install(config_path=config_path, **kwargs)
    return {"ok": False, "error": f"Unsupported platform: {plat}"}


def restart_daemon() -> Dict[str, Any]:
    """Restart the installed bot daemon service (graceful, daemon-aware).

    Returns ``ok: False`` when no service is installed for the platform so the
    caller can fall back to a direct drain + relaunch (Issue #3161).
    """
    plat = _detect_platform()
    if plat == "systemd":
        from .systemd import restart
        return restart()
    elif plat == "launchd":
        from .launchd import restart
        return restart()
    elif plat == "windows":
        from .windows import restart
        return restart()
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
    elif plat == "windows":
        from .windows import uninstall
        return uninstall()
    return {"ok": False, "error": f"Unsupported platform: {plat}"}
