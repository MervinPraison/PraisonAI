"""
Registry for sandbox implementations.

Maps sandbox types to their implementation classes (lazy-loaded).
Extensible: third-party sandboxes can register via entry points.
"""

from __future__ import annotations

from .._registry import PluginRegistry


def _docker_loader():
    from .docker import DockerSandbox
    return DockerSandbox


def _subprocess_loader():
    from .subprocess import SubprocessSandbox
    return SubprocessSandbox


def _sandlock_loader():
    from .sandlock import SandlockSandbox
    return SandlockSandbox


def _ssh_loader():
    from .ssh import SSHSandbox
    return SSHSandbox


def _modal_loader():
    from .modal_sandbox import ModalSandbox
    return ModalSandbox


def _daytona_loader():
    from .daytona import DaytonaSandbox
    return DaytonaSandbox


def _e2b_loader():
    from .e2b import E2BSandbox
    return E2BSandbox


# Built-in sandbox types with lazy loading
_BUILTIN_SANDBOXES = {
    "docker": _docker_loader,
    "subprocess": _subprocess_loader,
    "sandlock": _sandlock_loader,
    "ssh": _ssh_loader,
    "modal": _modal_loader,
    "daytona": _daytona_loader,
    "e2b": _e2b_loader,
}


class SandboxRegistry(PluginRegistry):
    """Registry for sandbox implementations."""
    
    def __init__(self):
        super().__init__(
            entry_point_group="praisonai.sandbox",
            builtins=_BUILTIN_SANDBOXES
        )