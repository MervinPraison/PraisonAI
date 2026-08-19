"""Lazy access to compute providers from praisonaiagents.

Concrete ``ComputeProviderProtocol`` implementations live in the ``praisonai``
wrapper package (``praisonai.integrations.compute``). The core SDK only ships
protocols, so this module resolves a provider by name at call time -- mirroring
``praisonaiagents.sandbox._sandbox_bridge``.
"""

from __future__ import annotations

import importlib
from typing import Any, Optional

_INSTALL_HINT = "Remote compute requires the wrapper package: pip install praisonai"

# name -> (module, attribute). Kept in sync with
# praisonai.integrations.managed_local._resolve_compute
_PROVIDERS = {
    "local": ("praisonai.integrations.compute.local", "LocalCompute"),
    "docker": ("praisonai.integrations.compute.docker", "DockerCompute"),
    "e2b": ("praisonai.integrations.compute.e2b", "E2BCompute"),
    "modal": ("praisonai.integrations.compute.modal_compute", "ModalCompute"),
    "daytona": ("praisonai.integrations.compute.daytona", "DaytonaCompute"),
    "flyio": ("praisonai.integrations.compute.flyio", "FlyioCompute"),
    "tenki": ("praisonai.integrations.compute.tenki", "TenkiCompute"),
}

_EXTRA_HINTS = {
    "e2b": "pip install praisonai[e2b]",
    "modal": "pip install praisonai[modal]",
    "daytona": "pip install praisonai[daytona]",
}


# Places that live only in praisonai-sandbox. They speak SandboxProtocol
# (one object IS one environment) rather than ComputeProviderProtocol (one
# object hands out many), so an adapter supplies the missing half.
from ._sandbox_adapter import NEEDS_INSTANCE, SANDBOX_ONLY  # noqa: E402

# Spellings users already have in their code, mapped to the canonical name.
_ALIASES = {"native": "sandlock"}


def available_providers() -> list:
    """Every place ``tools_run_on=`` / ``run_in=`` accepts, from both registries."""
    return sorted(set(_PROVIDERS) | set(SANDBOX_ONLY))


def compute_package_available() -> bool:
    """True when the wrapper package supplying compute providers is importable."""
    import importlib.util

    return importlib.util.find_spec("praisonai") is not None


def resolve_compute(compute: Optional[Any]) -> Optional[Any]:
    """Resolve ``compute`` into a ``ComputeProviderProtocol`` instance.

    Accepts ``None`` (no remote compute), a provider name such as ``"docker"``,
    or an already-instantiated provider, which is returned unchanged so callers
    can inject custom or pre-configured backends.
    """
    if compute is None:
        return None

    # Already a provider instance (duck-typed against ComputeProviderProtocol).
    if not isinstance(compute, str):
        if hasattr(compute, "provision") and hasattr(compute, "execute"):
            return compute
        # A SandboxProtocol instance -- e.g. SSHSandbox(host=...) -- is adapted,
        # which is the only way to pass connection details.
        if hasattr(compute, "run_command") and hasattr(compute, "start"):
            from ._sandbox_adapter import wrap_sandbox_instance

            return wrap_sandbox_instance(compute)
        raise TypeError(
            f"compute= expects a provider name or a ComputeProviderProtocol "
            f"instance, got {type(compute).__name__}"
        )

    name = compute.lower().strip()
    name = _ALIASES.get(name, name)

    # A sandbox-only place: adapt it to the compute-provider shape.
    if name in SANDBOX_ONLY:
        if name in NEEDS_INSTANCE:
            raise ValueError(
                f"{name!r} needs connection details a bare name cannot carry. "
                f"Instead, {NEEDS_INSTANCE[name]}"
            )
        from ._sandbox_adapter import SandboxComputeAdapter

        return SandboxComputeAdapter(name)

    if name not in _PROVIDERS:
        raise ValueError(
            f"Unknown place {name!r}. "
            f"Available: {', '.join(available_providers())}"
        )

    module_name, attr = _PROVIDERS[name]
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        hint = _EXTRA_HINTS.get(name, _INSTALL_HINT)
        raise ImportError(f"compute={name!r} requires {module_name}. {hint}") from exc

    return getattr(module, attr)()
