"""Self-management helpers for the PraisonAI CLI binary.

This module powers ``praisonai upgrade`` / ``praisonai uninstall`` and the
non-blocking "update available" hint. It is deliberately install-lifecycle /
CLI-only: it never imports or mutates ``praisonaiagents`` and only reasons about
how the *CLI binary* was installed onto the machine (an isolated ``uv tool`` /
``pipx`` environment, or a plain ``pip`` install).

Detection order mirrors the one-line installer (``install.sh``): prefer the
managed, isolated tool managers (``uv tool`` then ``pipx``) and fall back to the
current interpreter's ``pip`` for library/embedded installs.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# Package the standalone installer provisions (``uv tool install praisonai``).
PACKAGE_NAME = "praisonai"
# PyPI JSON endpoint used for the (network, best-effort) latest-version lookup.
_PYPI_URL = f"https://pypi.org/pypi/{PACKAGE_NAME}/json"
# Env var that opts out of the background "update available" hint.
UPDATE_CHECK_ENV = "PRAISONAI_NO_UPDATE_CHECK"
# How long a cached update check stays fresh before we re-check.
_UPDATE_CHECK_TTL_SECONDS = 60 * 60 * 24  # 24h


@dataclass
class InstallInfo:
    """Describes how the running ``praisonai`` binary was installed.

    ``manager`` is one of ``"uv"``, ``"pipx"`` or ``"pip"``. ``upgrade_cmd`` /
    ``uninstall_cmd`` are argv lists that operate on the managed install in
    place; ``None`` means the operation is unsupported for that manager.
    """

    manager: str
    upgrade_cmd: Optional[List[str]]
    uninstall_cmd: Optional[List[str]]

    @property
    def is_managed(self) -> bool:
        """True when installed into an isolated tool env (uv/pipx)."""
        return self.manager in ("uv", "pipx")


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def _pipx_manages_package() -> bool:
    """Return True when pipx reports ``praisonai`` as a managed venv."""
    pipx = _which("pipx")
    if not pipx:
        return False
    try:
        result = subprocess.run(
            [pipx, "list", "--json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0 or not result.stdout:
            return False
        data = json.loads(result.stdout)
        venvs = data.get("venvs", {})
        return PACKAGE_NAME in venvs
    except Exception:
        return False


def _uv_manages_package() -> bool:
    """Return True when ``uv tool`` reports ``praisonai`` as installed."""
    uv = _which("uv")
    if not uv:
        return False
    try:
        result = subprocess.run(
            [uv, "tool", "list"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0 or not result.stdout:
            return False
        for line in result.stdout.splitlines():
            if line.strip().split(" ")[0] == PACKAGE_NAME:
                return True
        return False
    except Exception:
        return False


def detect_install() -> InstallInfo:
    """Detect how the CLI was installed and how to upgrade/uninstall it.

    Prefers an isolated tool manager (``uv tool`` then ``pipx``) so the managed
    one-line install path is upgraded/removed cleanly; otherwise falls back to a
    plain ``pip`` install against the current interpreter.
    """
    uv = _which("uv")
    if uv and _uv_manages_package():
        return InstallInfo(
            manager="uv",
            upgrade_cmd=[uv, "tool", "upgrade", PACKAGE_NAME],
            uninstall_cmd=[uv, "tool", "uninstall", PACKAGE_NAME],
        )

    pipx = _which("pipx")
    if pipx and _pipx_manages_package():
        return InstallInfo(
            manager="pipx",
            upgrade_cmd=[pipx, "upgrade", PACKAGE_NAME],
            uninstall_cmd=[pipx, "uninstall", PACKAGE_NAME],
        )

    # Fall back to pip against the current interpreter (library/embedded use).
    return InstallInfo(
        manager="pip",
        upgrade_cmd=[
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            PACKAGE_NAME,
        ],
        uninstall_cmd=[
            sys.executable,
            "-m",
            "pip",
            "uninstall",
            "-y",
            PACKAGE_NAME,
        ],
    )


def get_installed_version() -> str:
    """Return the installed wrapper/CLI version (best-effort)."""
    try:
        from praisonai_code._version import get_wrapper_version

        wrapper = get_wrapper_version()
        if wrapper:
            return wrapper
    except Exception:
        pass
    try:
        from praisonai_code._version import get_package_version

        return get_package_version()
    except Exception:
        return "unknown"


def get_latest_version(timeout: float = 5.0) -> Optional[str]:
    """Return the latest ``praisonai`` version on PyPI, or ``None`` on failure."""
    try:
        with urllib.request.urlopen(_PYPI_URL, timeout=timeout) as response:
            data = json.loads(response.read().decode())
        version = data.get("info", {}).get("version")
        return version if isinstance(version, str) and version else None
    except Exception:
        return None


def _version_tuple(value: str) -> tuple:
    parts: List[int] = []
    for chunk in value.split("."):
        num = ""
        for ch in chunk:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    return tuple(parts)


def is_newer(latest: str, current: str) -> bool:
    """Return True when ``latest`` is a strictly newer version than ``current``."""
    try:
        return _version_tuple(latest) > _version_tuple(current)
    except Exception:
        return latest != current


# --- Non-blocking update-check cache -------------------------------------

def _state_dir() -> Path:
    from ..configuration.paths import get_user_config_dir

    return get_user_config_dir() / "state"


def _update_cache_path() -> Path:
    return _state_dir() / "update_check.json"


def update_check_disabled() -> bool:
    """Return True when the background update hint is opted out."""
    value = os.environ.get(UPDATE_CHECK_ENV, "").strip().lower()
    return value in ("1", "true", "yes", "on")


def read_cached_hint() -> Optional[str]:
    """Return a cached "newer version available" hint, if fresh.

    Never performs network I/O and never raises: a corrupt/missing/stale cache
    simply yields ``None`` so start-up is never blocked or broken.
    """
    if update_check_disabled():
        return None
    try:
        path = _update_cache_path()
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        checked_at = float(data.get("checked_at", 0))
        if time.time() - checked_at > _UPDATE_CHECK_TTL_SECONDS:
            return None
        latest = data.get("latest")
        current = get_installed_version()
        if isinstance(latest, str) and latest and is_newer(latest, current):
            return (
                f"A newer PraisonAI is available: {current} -> {latest}. "
                "Run: praisonai upgrade"
            )
        return None
    except Exception:
        return None


def refresh_update_cache(timeout: float = 5.0) -> None:
    """Fetch the latest version and persist it to the cache (best-effort)."""
    if update_check_disabled():
        return
    latest = get_latest_version(timeout=timeout)
    if not latest:
        return
    try:
        state_dir = _state_dir()
        state_dir.mkdir(parents=True, exist_ok=True)
        _update_cache_path().write_text(
            json.dumps({"latest": latest, "checked_at": time.time()}),
            encoding="utf-8",
        )
    except Exception:
        # A read-only home or unwritable state dir must never break the CLI.
        return


def _cache_is_fresh() -> bool:
    """Return True when the update cache exists and is within its TTL."""
    try:
        path = _update_cache_path()
        if not path.exists():
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        checked_at = float(data.get("checked_at", 0))
        return (time.time() - checked_at) <= _UPDATE_CHECK_TTL_SECONDS
    except Exception:
        return False


def maybe_schedule_update_check() -> None:
    """Warm the update cache in a fully detached background process.

    Called once per CLI start. Performs **no** network I/O in the caller and
    never blocks or raises: if the cache is missing/stale it spawns a
    short-lived detached child that refreshes it for the *next* invocation. If
    the cache is already fresh, or checks are disabled, this is a no-op.
    """
    if update_check_disabled():
        return
    try:
        if _cache_is_fresh():
            return
        # Detached, output-suppressed child so the parent CLI never waits on it.
        code = (
            "from praisonai_code.cli.features.self_manage import "
            "refresh_update_cache; refresh_update_cache()"
        )
        kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }
        if os.name == "posix":
            kwargs["start_new_session"] = True
        else:  # pragma: no cover - Windows-only detach flag
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
                subprocess, "DETACHED_PROCESS", 0
            )
            if creationflags:
                kwargs["creationflags"] = creationflags
        subprocess.Popen([sys.executable, "-c", code], **kwargs)
    except Exception:
        # Best-effort only: a spawn failure must never break start-up.
        return
