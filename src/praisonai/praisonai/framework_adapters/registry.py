"""
Framework Adapter Registry for PraisonAI.

Provides a registry pattern for managing framework adapters with entry points support,
enabling dynamic registration and discovery of framework adapters.
Uses dependency injection instead of singleton pattern.
"""

from __future__ import annotations

from typing import Dict, Type, Optional
import inspect
import logging
import threading

from .base import FrameworkAdapter
from .._registry import PluginRegistry

logger = logging.getLogger(__name__)


def _crewai_loader():
    from .crewai_adapter import CrewAIAdapter
    return CrewAIAdapter

def _autogen_loader():
    from .autogen_adapter import AutoGenFamilyAdapter
    return AutoGenFamilyAdapter

def _autogen_v2_loader():
    from .autogen_adapter import AutoGenAdapter
    return AutoGenAdapter

def _autogen_v4_loader():
    from .autogen_adapter import AutoGenV4Adapter
    return AutoGenV4Adapter

def _ag2_loader():
    from .autogen_adapter import AG2Adapter
    return AG2Adapter

def _praisonai_loader():
    from .praisonai_adapter import PraisonAIAdapter
    return PraisonAIAdapter

# Built-in: native PraisonAI adapter only. CrewAI/AutoGen register via entry points
# (wrapper shims below, or external ``praisonai-frameworks`` when installed).
_BUILTIN_ADAPTERS = {
    "praisonai": _praisonai_loader,
}

class FrameworkAdapterRegistry(PluginRegistry[FrameworkAdapter]):
    """
    Registry for framework adapters.
    
    Provides centralized management of framework adapters with support
    for dynamic registration, entry points discovery, and availability checking.
    
    Uses dependency injection pattern instead of singleton.
    """

    # Default selection priority used when no framework is requested
    # explicitly. Entry-point plugins registered under the
    # ``praisonai.framework_adapters`` group are consulted after this list,
    # so a third-party adapter can become the default once the built-ins are
    # unavailable.
    # ``ag2`` is intentionally omitted: its adapter is an unimplemented stub and
    # is not registered in ``_BUILTIN_ADAPTERS``, so advertising it as a default
    # dispatch target would let ``pick_default`` route to a NotImplementedError.
    DEFAULT_PRIORITY: tuple[str, ...] = ("praisonai", "crewai", "autogen")

    def __init__(self, *, discover_entry_points: bool = True) -> None:
        """Initialize the registry with built-in adapters."""
        super().__init__(
            entry_point_group="praisonai.framework_adapters",
            builtins=_BUILTIN_ADAPTERS,
            discover_entry_points=discover_entry_points,
        )
        # Hot-path caches: availability is probed once per process (invalidatable
        # in tests), and protocol validation runs once per adapter class rather
        # than on every create()/run()/arun(). Both are guarded by a lock so
        # multi-tenant/threaded callers don't race.
        self._avail_cache: dict[str, bool] = {}
        self._avail_lock = threading.Lock()
        self._validated_classes: set[type] = set()

    def pick_default(self) -> str:
        """Return the name of the default framework to use.

        Resolution policy (single source of truth for default selection):

        1. Walk ``DEFAULT_PRIORITY`` and return the first available adapter.
        2. Fall back to any other registered adapter (e.g. entry-point
           plugins) that reports availability.

        Returns:
            str: Name of the first available framework adapter.

        Raises:
            RuntimeError: If no registered adapter is available.
        """
        for name in self.DEFAULT_PRIORITY:
            try:
                if self.is_available(name):
                    return name
            except (ValueError, TypeError):
                continue

        # Entry-point / runtime-registered adapters get a chance to be the
        # default once none of the built-in priorities are installed.
        for name in self.list_names():
            if name in self.DEFAULT_PRIORITY:
                continue
            try:
                if self.is_available(name):
                    return name
            except (ValueError, TypeError):
                continue

        raise RuntimeError(
            "No supported framework installed. Available adapters: "
            f"{self.list_all_names()}"
        )
    
    def _validate_adapter(self, name: str, adapter) -> None:
        """Validate that adapter implements the required protocol signature.

        Signature inspection is memoised per adapter *class* so repeated
        ``create()`` calls on the hot path do not re-run ``inspect.signature``.
        """
        cls = type(adapter)
        if cls in self._validated_classes:
            return

        if getattr(adapter, "is_router", False):
            self._validated_classes.add(cls)
            return

        _REQUIRED_KW = {"tools_dict", "agent_callback", "task_callback", "cli_config"}

        def _accepts_required(fn) -> Optional[str]:
            params = inspect.signature(fn).parameters.values()
            # A **kwargs catch-all accepts every required keyword by definition,
            # so entry-point plugins that forward **kwargs to a delegate (the
            # advertised extension surface) validate instead of being silently
            # dropped from pick_default()/list_available_frameworks().
            if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params):
                return None
            named = {
                p.name for p in params
                if p.kind in (inspect.Parameter.KEYWORD_ONLY,
                              inspect.Parameter.POSITIONAL_OR_KEYWORD)
            }
            missing = _REQUIRED_KW - named
            return f"missing keyword parameters {sorted(missing)}" if missing else None

        for method_name in ("run", "arun"):
            fn = getattr(cls, method_name, None)
            if fn is None:
                continue  # arun is optional; sync-only adapters keep working
            err = _accepts_required(fn)
            if err:
                raise TypeError(
                    f"FrameworkAdapter {name!r}.{method_name} does not implement "
                    f"the protocol: {err}"
                )
        self._validated_classes.add(cls)

    def create(self, name: str, *args, **kwargs):
        """Create an adapter instance with protocol validation."""
        adapter = super().create(name, *args, **kwargs)
        self._validate_adapter(name, adapter)
        return adapter

    def list_available_frameworks(self) -> list[str]:
        """Return registered framework names that report availability."""
        return sorted(
            name for name in self.list_names() if self.is_available(name)
        )

    # Backward compatibility aliases - delegate to parent methods
    def list_registered(self) -> list[str]:
        """
        List all registered framework adapter names.
        
        Returns:
            list[str]: Sorted list of registered adapter names
        """
        return self.list_names()

    def is_available(self, name: str) -> bool:
        """
        Check if a framework adapter is available and functional.

        The probe (adapter construction + ``adapter.is_available()``, which may
        run import machinery for a third-party package) is memoised per process
        so hot-path callers like ``pick_default`` — invoked on every default
        ``run()``/``arun()`` — do not re-probe. Use
        :meth:`invalidate_availability` to drop cached results in tests.

        Args:
            name: Name of the adapter to check

        Returns:
            bool: True if adapter exists and is available
        """
        # Normalize the cache key the same way the underlying registry resolves
        # names (case-insensitive, see PluginRegistry.resolve). Without this,
        # is_available("CrewAI") and invalidate_availability("crewai") would key
        # different cache entries, leaving the documented escape hatch inert.
        key = name.lower()
        with self._avail_lock:
            cached = self._avail_cache.get(key)
        if cached is not None:
            return cached

        try:
            adapter = self.create(name)
            # ImportError covers ModuleNotFoundError raised when an adapter's
            # constructor touches a missing optional dependency; treat the
            # framework as simply unavailable rather than leaking a raw import
            # error to callers (CLI validation, doctor checks, pick_default).
            ok = bool(adapter.is_available())
        except (ValueError, TypeError, ImportError):
            ok = False
        except Exception:
            logger.warning("is_available() raised for adapter %r", name, exc_info=True)
            ok = False

        with self._avail_lock:
            self._avail_cache[key] = ok
        return ok

    def invalidate_availability(self, name: Optional[str] = None) -> None:
        """Drop cached availability probe results.

        Test hook / runtime escape hatch for when an optional framework is
        installed or removed after the first probe.

        Args:
            name: Adapter name to invalidate, or ``None`` to clear the whole cache.
        """
        with self._avail_lock:
            if name is None:
                self._avail_cache.clear()
            else:
                # Match the case-insensitive key used by is_available().
                self._avail_cache.pop(name.lower(), None)


# Default registry access - replaced by FrameworkAdapterRegistry.default()
def get_default_registry() -> FrameworkAdapterRegistry:
    """Return the process-default registry. Prefer DI; use this only at the edge."""
    return FrameworkAdapterRegistry.default()


def list_framework_choices(*, include_unavailable: bool = False) -> list[str]:
    """Single source of truth for CLI/YAML framework name lists.

    Discovers built-in adapters *and* third-party adapters registered via the
    ``praisonai.framework_adapters`` entry-point group, so newly installed
    adapters appear automatically wherever framework names are shown or
    validated (argparse ``choices``, doctor checks, etc.).

    Args:
        include_unavailable: When True, return every registered adapter name;
            otherwise only those reporting availability.

    Returns:
        Sorted list of framework adapter names.
    """
    registry = get_default_registry()
    if include_unavailable:
        return sorted(registry.list_names())
    return registry.list_available_frameworks()


def list_available_frameworks() -> list[str]:
    """Return registered framework names that report availability."""
    return get_default_registry().list_available_frameworks()


def get_install_hint(name: str, *, registry: Optional[FrameworkAdapterRegistry] = None) -> str:
    """Return install hint for a framework, consulting the adapter when registered.

    Falls back to ``pip install 'praisonai[<extra>]'`` when the adapter cannot
    be resolved (e.g. its dependencies are missing) or does not declare a hint.

    Args:
        name: Framework name to build the install hint for.
        registry: Optional adapter registry to consult; defaults to the
            process-default registry when omitted (DI-friendly).
    """
    registry = registry or get_default_registry()
    try:
        adapter = registry.create(name)
        hint = getattr(adapter, "install_hint", None)
        if hint:
            return hint
    except (ValueError, TypeError, ImportError):
        pass
    extra_name = {
        "autogen_v4": "autogen-v4",
        "openai_agents": "openai-agents",
        "google_adk": "google-adk",
        "pydantic_ai": "pydantic-ai",
    }.get(name, name)
    return f"pip install 'praisonai-frameworks[{extra_name}]'"


def framework_option_help() -> str:
    """Help text for CLI --framework options (registry-driven)."""
    try:
        names = list_framework_choices(include_unavailable=True)
    except ImportError:
        return "Framework: praisonai, crewai, autogen"
    if names:
        return "Framework: " + ", ".join(names)
    return "Framework: praisonai, crewai, autogen"
