"""Compute providers: one object that hands out many environments.

The sibling modules in ``praisonai_sandbox`` implement ``SandboxProtocol`` --
one object *is* one environment. These implement ``ComputeProviderProtocol``:
one object provisions, tracks and reclaims *many*, which is what
``tools_run_on=`` and ``run_on=`` need and what ``praisonai managed ps`` reads.

They live here rather than in the wrapper because they are vendor integrations,
and this is the package that already carries one optional extra per vendor.
Reaching E2B through the wrapper resolved 143 packages -- every vendor SDK, for
one provider -- against 58 for ``praisonai-sandbox[e2b]``.

Imports stay lazy: naming a provider must not import the others' SDKs.
"""

from __future__ import annotations

__all__ = [
    "DockerCompute", "E2BCompute", "ModalCompute", "DaytonaCompute",
    "FlyioCompute", "TenkiCompute", "LocalCompute", "SyncComputeProvider",
]


def __getattr__(name: str):
    """Import a provider only when it is actually named."""
    sources = {
        "DockerCompute": ".docker",
        "E2BCompute": ".e2b",
        "ModalCompute": ".modal_compute",
        "DaytonaCompute": ".daytona",
        "FlyioCompute": ".flyio",
        "TenkiCompute": ".tenki",
        "LocalCompute": ".local",
        "SyncComputeProvider": "._sync_base",
    }
    if name not in sources:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(sources[name], __name__)
    return getattr(module, name)
