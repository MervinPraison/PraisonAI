"""Model-aware runtime profiles for PraisonAI Agents.

This module provides an opt-in, protocol-driven registry that maps a model
family (resolved from a model id/provider) to a ``RuntimeProfile``: optional
system-prompt segment overrides and a preferred edit-tool format, plus room for
family-specific knobs.

Design follows AGENTS.md and mirrors ``runtime/registry.py``:
- Core protocol only (no heavy implementations at module level)
- Thread-safe registration with a global registry
- Built-in, data-driven default profiles (tuning needs no code changes)
- Entry-point discovery for third-party profiles
  (``praisonaiagents.runtime_profiles``)
- Backward compatible: the ``default`` profile is a pure no-op, so with no
  profile configured the generated prompt and advertised tools are unchanged.
"""

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

__all__ = [
    "RuntimeProfile",
    "RuntimeProfileProtocol",
    "RuntimeProfileRegistry",
    "register_profile",
    "resolve_profile",
    "list_profiles",
    "resolve_model_family",
]

DEFAULT_PROFILE_NAME = "default"


@runtime_checkable
class RuntimeProfileProtocol(Protocol):
    """Protocol for a model-aware runtime profile.

    A profile can adjust the assembled system prompt (segment-level, so caching,
    rules and memory injection are preserved) and declare a preferred edit-tool
    format used when materialising built-in coding tools.
    """

    name: str
    preferred_edit_format: Optional[str]

    def apply_system_prompt(self, system_prompt: str) -> str:
        """Return the (possibly) adjusted system prompt.

        Implementations must return ``system_prompt`` unchanged when they have
        no overrides so behaviour stays backward compatible.
        """
        ...


@dataclass
class RuntimeProfile:
    """Data-driven runtime profile for a model family.

    Attributes:
        name: Profile / family identifier (e.g. ``"anthropic"``, ``"default"``).
        system_prompt_prefix: Optional text prepended to the assembled prompt.
        system_prompt_suffix: Optional text appended to the assembled prompt.
        preferred_edit_format: Preferred built-in edit-tool format, e.g.
            ``"patch"`` (apply_patch), ``"string-replace"`` (edit_file), or
            ``"whole-file"`` (write_file). ``None`` keeps today's defaults.
        extras: Free-form family-specific knobs for future tuning.
    """

    name: str = DEFAULT_PROFILE_NAME
    system_prompt_prefix: Optional[str] = None
    system_prompt_suffix: Optional[str] = None
    preferred_edit_format: Optional[str] = None
    extras: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_prompt_neutral(self) -> bool:
        """True when the profile does not alter the assembled system prompt."""
        return not self.system_prompt_prefix and not self.system_prompt_suffix

    @property
    def is_default(self) -> bool:
        """True when this profile does not change any behaviour at all.

        (No prompt overrides and no preferred edit-tool format.)
        """
        return self.is_prompt_neutral and self.preferred_edit_format is None

    def apply_system_prompt(self, system_prompt: str) -> str:
        """Apply prefix/suffix overrides to an already-assembled prompt.

        The ``default`` profile (and any profile with no overrides) returns the
        input unchanged, guaranteeing byte-for-byte identical output to today.
        """
        if system_prompt is None:
            return system_prompt
        if self.is_prompt_neutral:
            return system_prompt
        result = system_prompt
        if self.system_prompt_prefix:
            result = f"{self.system_prompt_prefix}\n\n{result}"
        if self.system_prompt_suffix:
            result = f"{result}\n\n{self.system_prompt_suffix}"
        return result


def _get_builtin_profiles() -> Dict[str, RuntimeProfile]:
    """Built-in, data-driven profiles.

    Only the ``default`` profile is behaviour-neutral. Family profiles are
    opt-in (resolved only when the caller passes a matching model) and carry a
    preferred edit format without changing prompt text unless configured.
    """
    return {
        DEFAULT_PROFILE_NAME: RuntimeProfile(name=DEFAULT_PROFILE_NAME),
        "anthropic": RuntimeProfile(
            name="anthropic",
            preferred_edit_format="string-replace",
        ),
        "openai": RuntimeProfile(
            name="openai",
            preferred_edit_format="patch",
        ),
        "gemini": RuntimeProfile(
            name="gemini",
            preferred_edit_format="whole-file",
        ),
    }


def resolve_model_family(model: Optional[str]) -> str:
    """Resolve a coarse model family from a model id/provider string.

    Mirrors the narrow branching in ``llm/llm.py`` (Anthropic / Gemini / OpenAI)
    without importing it, so this module stays lightweight and core.
    Unknown models resolve to ``"default"``.
    """
    if not model or not isinstance(model, str):
        return DEFAULT_PROFILE_NAME

    m = model.lower()
    provider = m.split("/", 1)[0] if "/" in m else ""

    if provider == "anthropic" or "claude" in m:
        return "anthropic"
    if provider in {"gemini", "google"} or m.startswith("gemini"):
        return "gemini"
    if provider == "openai" or m.startswith("gpt") or m.startswith("o1") or m.startswith("o3"):
        return "openai"
    return DEFAULT_PROFILE_NAME


class RuntimeProfileRegistry:
    """Thread-safe registry of runtime profiles keyed by family/name."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._profiles: Dict[str, RuntimeProfile] = {}
        self._builtin_initialized = False

    def _ensure_builtin(self) -> None:
        if self._builtin_initialized:
            return
        with self._lock:
            if self._builtin_initialized:
                return
            for name, profile in _get_builtin_profiles().items():
                self._profiles.setdefault(name, profile)
            self._builtin_initialized = True

    def register(self, name: str, profile: RuntimeProfile, override: bool = True) -> None:
        """Register (or replace) a profile.

        Args:
            name: Family/profile identifier.
            profile: The ``RuntimeProfile`` to register.
            override: When False, raise if ``name`` already exists.
        """
        if not isinstance(profile, RuntimeProfile):
            raise TypeError("profile must be a RuntimeProfile instance")
        self._ensure_builtin()
        with self._lock:
            if not override and name in self._profiles:
                raise ValueError(f"Profile '{name}' is already registered")
            self._profiles[name] = profile

    def resolve(self, model: Optional[str] = None, name: Optional[str] = None) -> RuntimeProfile:
        """Resolve a profile by explicit ``name`` or by ``model`` family.

        Falls back to the behaviour-neutral ``default`` profile when no match is
        found, guaranteeing backward compatibility.
        """
        self._ensure_builtin()
        key = name or resolve_model_family(model)
        with self._lock:
            return self._profiles.get(key) or self._profiles[DEFAULT_PROFILE_NAME]

    def list_profiles(self) -> List[str]:
        """List all registered profile names."""
        self._ensure_builtin()
        with self._lock:
            return sorted(self._profiles.keys())

    def clear(self) -> None:
        """Clear all profiles (primarily for tests)."""
        with self._lock:
            self._profiles.clear()
            self._builtin_initialized = False


_global_registry = RuntimeProfileRegistry()


def register_profile(name: str, profile: RuntimeProfile, override: bool = True) -> None:
    """Register a runtime profile with the global registry."""
    _global_registry.register(name, profile, override=override)


def resolve_profile(model: Optional[str] = None, name: Optional[str] = None) -> RuntimeProfile:
    """Resolve a runtime profile by model family (or explicit name).

    With no matching profile this returns the ``default`` profile, whose
    ``apply_system_prompt`` is a pure no-op.
    """
    return _global_registry.resolve(model=model, name=name)


def list_profiles() -> List[str]:
    """List all registered runtime profile names."""
    return _global_registry.list_profiles()


def _discover_entry_point_profiles() -> None:
    """Discover third-party profiles via the entry-point group.

    Entry points in group ``praisonaiagents.runtime_profiles`` should load to a
    ``RuntimeProfile`` instance or a zero-arg factory returning one.
    """
    try:
        from importlib.metadata import entry_points

        eps = entry_points(group="praisonaiagents.runtime_profiles")
        for ep in eps:
            try:
                obj = ep.load()
                profile = obj() if callable(obj) and not isinstance(obj, RuntimeProfile) else obj
                if isinstance(profile, RuntimeProfile):
                    _global_registry.register(ep.name, profile)
            except Exception:
                # Plugins are optional; ignore individual discovery failures.
                continue
    except Exception:
        # entry_points unavailable or errored; discovery is best-effort.
        pass


_discover_entry_point_profiles()
