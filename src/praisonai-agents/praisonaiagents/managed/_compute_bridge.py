"""Lazy access to compute providers from praisonaiagents.

Concrete ``ComputeProviderProtocol`` implementations live in the ``praisonai``
wrapper package (``praisonai.integrations.compute``). The core SDK only ships
protocols, so this module resolves a provider by name at call time -- mirroring
``praisonaiagents.sandbox._sandbox_bridge``.
"""

from __future__ import annotations

import importlib
from typing import Any, Optional

_INSTALL_HINT = "Remote compute requires: pip install praisonai-sandbox"

# name -> (module, attribute). Kept in sync with
# praisonai.integrations.managed_local._resolve_compute
_PROVIDERS = {
    "local": ("praisonai_sandbox.compute.local", "LocalCompute"),
    "docker": ("praisonai_sandbox.compute.docker", "DockerCompute"),
    "e2b": ("praisonai_sandbox.compute.e2b", "E2BCompute"),
    "modal": ("praisonai_sandbox.compute.modal_compute", "ModalCompute"),
    "daytona": ("praisonai_sandbox.compute.daytona", "DaytonaCompute"),
    "flyio": ("praisonai_sandbox.compute.flyio", "FlyioCompute"),
    "tenki": ("praisonai_sandbox.compute.tenki", "TenkiCompute"),
}

# What to actually type when a provider is missing. Every name here must point
# at an extra that EXISTS and installs something -- three of these used to name
# extras that were absent or empty, so a user followed the official hint, waited
# for the install, and hit the identical failure again.
#
# The providers in _PROVIDERS now live in praisonai-sandbox, so the failing
# import is `praisonai_sandbox.compute.*`: point the hint at the lightweight
# package that owns the module, not the heavy wrapper. Reaching E2B through
# praisonai-sandbox[e2b] resolves 58 packages against 143 through praisonai.
# Sandbox-only places (novita/sandlock/ssh) resolve through the
# SandboxComputeAdapter and only need `praisonai-sandbox`.
_EXTRA_HINTS = {
    "e2b": "pip install 'praisonai-sandbox[e2b]'",
    "modal": "pip install 'praisonai-sandbox[modal]'",
    "daytona": "pip install 'praisonai-sandbox[daytona]'",
    "docker": "pip install 'praisonai-sandbox[docker]'",
    "novita": "pip install 'praisonai-sandbox[novita]'",
    "sandlock": "pip install 'praisonai-sandbox[sandlock]'",
    "ssh": "pip install 'praisonai-sandbox[ssh]'",
    # flyio and tenki need a credential rather than an SDK; flyio speaks plain
    # HTTP through aiohttp, which praisonaiagents already requires. Export the
    # variable so a child process inherits it -- a bare assignment would not.
    "flyio": "export FLY_API_TOKEN=... (see https://fly.io/docs/flyctl/auth-token)",
    "tenki": "pip install 'praisonai-sandbox[tenki]'",
}


# Places that live only in praisonai-sandbox. They speak SandboxProtocol
# (one object IS one environment) rather than ComputeProviderProtocol (one
# object hands out many), so an adapter supplies the missing half.
from ._sandbox_adapter import NEEDS_INSTANCE, SANDBOX_ONLY  # noqa: E402

# Spellings users already have in their code, mapped to the canonical name.
_ALIASES = {"native": "sandlock"}


def _entry_point_providers() -> dict:
    """Places contributed by other installed packages.

    The sandbox and managed-backend registries already discover plugins this
    way (``praisonai.sandbox``, ``praisonai.managed_backends``); the compute
    registry was the one hardcoded dict, so adding a place meant editing core.
    A provider can now ship in its own distribution:

        [project.entry-points."praisonai.compute"]
        runpod = "praisonai_compute_runpod:RunpodCompute"
    """
    found = {}
    try:
        from importlib.metadata import entry_points

        for ep in entry_points(group="praisonai.compute"):
            found[ep.name.lower()] = ep
    except Exception:  # pragma: no cover - discovery must never break resolution
        pass
    return found


def available_providers() -> list:
    """Every place ``tools_run_on=`` / ``run_in=`` accepts, from all registries."""
    return sorted(
        set(_PROVIDERS) | set(SANDBOX_ONLY) | set(_entry_point_providers())
    )


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

    external = _entry_point_providers()
    if name in external and name not in _PROVIDERS:
        # Let a contributed place describe itself. Without this the repr falls
        # back to the bare name, because the phrase table is a literal that
        # cannot know about packages installed later.
        _remember_display_name(name, external[name])
        # A place contributed by another package. Loaded on demand, so an
        # installed-but-broken plugin cannot break anything that never names it.
        return external[name].load()()

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


#: Display phrases contributed by external providers, filled in on resolve.
_DISPLAY_NAMES: dict = {}


def _remember_display_name(name: str, entry_point) -> None:
    """Record a contributed provider's own phrase, if it declares one."""
    try:
        cls = entry_point.load()
        phrase = getattr(cls, "display_name", None)
        if isinstance(phrase, str) and phrase:
            _DISPLAY_NAMES[name] = phrase
    except Exception:  # pragma: no cover - naming must never break resolution
        pass


def contributed_display_name(name: str):
    """The phrase a contributed place declared for itself, if any."""
    return _DISPLAY_NAMES.get((name or "").lower())
