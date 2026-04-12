"""
Compute Provider Adapters for Managed Agents.

Concrete implementations of ComputeProviderProtocol for different
infrastructure backends.
"""

__all__ = [
    "DockerCompute",
    "LocalCompute",
    "DaytonaCompute",
    "E2BCompute",
    "ModalCompute",
    "FlyioCompute",
]


def __getattr__(name):
    if name == "DockerCompute":
        from .docker import DockerCompute
        return DockerCompute
    if name == "LocalCompute":
        from .local import LocalCompute
        return LocalCompute
    if name == "DaytonaCompute":
        from .daytona import DaytonaCompute
        return DaytonaCompute
    if name == "E2BCompute":
        from .e2b import E2BCompute
        return E2BCompute
    if name == "ModalCompute":
        from .modal_compute import ModalCompute
        return ModalCompute
    if name == "FlyioCompute":
        from .flyio import FlyioCompute
        return FlyioCompute
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
