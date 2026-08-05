"""
Sandbox implementations for PraisonAI.

Provides Docker, subprocess, sandlock, SSH, Modal, Daytona, E2B, and Novita sandbox for safe code execution.
"""

from typing import TYPE_CHECKING

from praisonai_sandbox._version import __version__

if TYPE_CHECKING:
    from .docker import DockerSandbox
    from .subprocess import SubprocessSandbox
    from .sandlock import SandlockSandbox
    from .ssh import SSHSandbox
    from .modal import ModalSandbox
    from .daytona import DaytonaSandbox
    from .e2b import E2BSandbox
    from .novita import NovitaSandbox


def __getattr__(name: str):
    """Lazy loading of sandbox components."""
    if name == "DockerSandbox":
        from .docker import DockerSandbox
        return DockerSandbox
    if name == "SubprocessSandbox":
        from .subprocess import SubprocessSandbox
        return SubprocessSandbox
    if name == "SandlockSandbox":
        from .sandlock import SandlockSandbox
        return SandlockSandbox
    if name == "SSHSandbox":
        from .ssh import SSHSandbox
        return SSHSandbox
    if name == "ModalSandbox":
        from .modal import ModalSandbox
        return ModalSandbox
    if name == "DaytonaSandbox":
        from .daytona import DaytonaSandbox
        return DaytonaSandbox
    if name == "E2BSandbox":
        from .e2b import E2BSandbox
        return E2BSandbox
    if name == "NovitaSandbox":
        from .novita import NovitaSandbox
        return NovitaSandbox
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DockerSandbox",
    "SubprocessSandbox",
    "SandlockSandbox",
    "SSHSandbox",
    "ModalSandbox",
    "DaytonaSandbox",
    "E2BSandbox",
    "NovitaSandbox",
    "__version__",
]
