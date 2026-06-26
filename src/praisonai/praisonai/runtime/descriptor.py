"""
Runtime descriptor: the lockfile that lets a thin ``run`` discover a warm runtime.

A running ``praisonai daemon`` writes a small JSON descriptor (host, port, token,
pid) into the project data directory. ``run`` reads it to decide whether to attach
to the warm runtime or fall back to in-process execution.

The descriptor is intentionally local-only: loopback host, file-permissioned
token, and a liveness check on the recorded pid.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

LOCK_FILENAME = "runtime.json"


def _runtime_dir(project_path: Optional[str] = None) -> Path:
    """Return the per-project directory that holds the runtime lockfile."""
    from praisonaiagents.paths import get_project_data_dir

    return Path(get_project_data_dir(project_path)) / "runtime"


def get_runtime_lock_path(project_path: Optional[str] = None) -> Path:
    """Return the path to the runtime lockfile for the current project."""
    return _runtime_dir(project_path) / LOCK_FILENAME


def _pid_alive(pid: int) -> bool:
    """Best-effort check that ``pid`` refers to a live process."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but is owned by another user.
        return True
    except OSError:
        return False
    return True


@dataclass
class RuntimeDescriptor:
    """Connection details for an active warm runtime.

    Attributes:
        host: Loopback host the runtime binds to (e.g. ``127.0.0.1``).
        port: TCP port the runtime listens on.
        token: Local auth token required by the runtime.
        pid: Process id of the runtime, used for liveness checks.
    """

    host: str
    port: int
    token: str
    pid: int

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def is_alive(self) -> bool:
        """Return True if the recorded pid still refers to a live process."""
        return _pid_alive(self.pid)

    def write(self, project_path: Optional[str] = None) -> Path:
        """Persist this descriptor to the project lockfile (mode 0600)."""
        path = get_runtime_lock_path(project_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(asdict(self), indent=2)
        # Create with 0600 from the start so the token is never world-readable
        # (avoids the TOCTOU window of write-then-chmod on shared hosts).
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(data)
        finally:
            # If the file pre-existed with looser perms, O_CREAT's mode is
            # ignored, so tighten explicitly as a belt-and-suspenders step.
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        return path

    @classmethod
    def read(cls, project_path: Optional[str] = None) -> Optional["RuntimeDescriptor"]:
        """Load a descriptor from the project lockfile, or None if absent/invalid."""
        path = get_runtime_lock_path(project_path)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text())
        except (OSError, ValueError):
            return None
        try:
            return cls(
                host=str(raw["host"]),
                port=int(raw["port"]),
                token=str(raw["token"]),
                pid=int(raw.get("pid", 0)),
            )
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def remove(project_path: Optional[str] = None) -> None:
        """Delete the project lockfile if present (idempotent)."""
        path = get_runtime_lock_path(project_path)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


def get_runtime_descriptor(
    project_path: Optional[str] = None,
    *,
    require_alive: bool = True,
) -> Optional[RuntimeDescriptor]:
    """Return the active runtime descriptor for this project.

    Args:
        project_path: Optional project root (defaults to cwd-derived project id).
        require_alive: When True (default), a descriptor whose pid is no longer
            alive is treated as stale: the lockfile is removed and None returned.

    Returns:
        A live :class:`RuntimeDescriptor`, or None when no usable runtime exists.
    """
    descriptor = RuntimeDescriptor.read(project_path)
    if descriptor is None:
        return None
    if require_alive and not descriptor.is_alive():
        # Stale lockfile from a runtime that has exited; clean it up.
        RuntimeDescriptor.remove(project_path)
        return None
    return descriptor
