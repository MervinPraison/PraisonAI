"""
Sandbox implementations for PraisonAI.

Provides Docker, subprocess, and sandlock sandbox for safe code execution.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .docker import DockerSandbox
    from .subprocess import SubprocessSandbox
    from .sandlock import SandlockSandbox

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
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["DockerSandbox", "SubprocessSandbox", "SandlockSandbox"]
