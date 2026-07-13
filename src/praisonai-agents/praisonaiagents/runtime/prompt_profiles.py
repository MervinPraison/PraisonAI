"""Opt-in prompt profiles for PraisonAI Agents.

A ``PromptProfile`` lets a caller adjust the assembled system prompt
(segment-level, so caching, rules and memory injection are preserved) without
subclassing the Agent. It is fully opt-in: with no profile configured the
generated prompt is byte-for-byte unchanged.

Design follows AGENTS.md and mirrors ``runtime/registry.py``:
- Core protocol only (no heavy implementations)
- Thread-safe registration with a global registry
- Entry-point discovery for third-party profiles
  (``praisonaiagents.prompt_profiles``)
- The reserved ``default`` profile is a pure no-op and can never be replaced by
  a prompt-altering profile, so unconfigured agents stay backward compatible.
"""

import threading
from dataclasses import dataclass, fields
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

__all__ = [
    "PromptProfile",
    "PromptProfileProtocol",
    "PromptProfileRegistry",
    "register_profile",
    "resolve_profile",
    "list_profiles",
]

DEFAULT_PROFILE_NAME = "default"


@runtime_checkable
class PromptProfileProtocol(Protocol):
    """Protocol for an opt-in prompt profile.

    A profile adjusts the assembled system prompt at the segment level, so
    caching, rules and memory injection are preserved.
    """

    name: str

    def apply_system_prompt(self, system_prompt: str) -> str:
        """Return the (possibly) adjusted system prompt.

        Implementations must return ``system_prompt`` unchanged when they have
        no overrides so behaviour stays backward compatible.
        """
        ...


@dataclass
class PromptProfile:
    """Data-driven prompt profile.

    Attributes:
        name: Profile identifier (e.g. ``"default"`` or a custom name).
        system_prompt_prefix: Optional text prepended to the assembled prompt.
        system_prompt_suffix: Optional text appended to the assembled prompt.
    """

    name: str = DEFAULT_PROFILE_NAME
    system_prompt_prefix: Optional[str] = None
    system_prompt_suffix: Optional[str] = None

    @property
    def is_prompt_neutral(self) -> bool:
        """True when the profile does not alter the assembled system prompt."""
        return not self.system_prompt_prefix and not self.system_prompt_suffix

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptProfile":
        """Build a profile from a config dict, validating keys.

        Unlike ``PromptProfile(**data)``, this raises a clear ``ValueError``
        listing unknown keys so an explicitly-configured profile with a typo is
        surfaced to the caller instead of being silently dropped.
        """
        if not isinstance(data, dict):
            raise TypeError("prompt_profile dict must be a mapping")
        allowed = {f.name for f in fields(cls)}
        unknown = set(data) - allowed
        if unknown:
            raise ValueError(
                "Unknown prompt_profile key(s): "
                f"{sorted(unknown)}; allowed keys are {sorted(allowed)}"
            )
        return cls(**data)

    def apply_system_prompt(self, system_prompt: str) -> str:
        """Apply prefix/suffix overrides to an already-assembled prompt.

        A prompt-neutral profile (including ``default``) returns the input
        unchanged, guaranteeing byte-for-byte identical output to today.
        """
        if system_prompt is None or self.is_prompt_neutral:
            return system_prompt
        result = system_prompt
        if self.system_prompt_prefix:
            result = f"{self.system_prompt_prefix}\n\n{result}"
        if self.system_prompt_suffix:
            result = f"{result}\n\n{self.system_prompt_suffix}"
        return result


class PromptProfileRegistry:
    """Thread-safe registry of prompt profiles keyed by name."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._profiles: Dict[str, PromptProfile] = {
            DEFAULT_PROFILE_NAME: PromptProfile(name=DEFAULT_PROFILE_NAME),
        }

    def register(self, name: str, profile: PromptProfile, override: bool = True) -> None:
        """Register (or replace) a profile.

        Args:
            name: Profile identifier.
            profile: The ``PromptProfile`` to register.
            override: When False, raise if ``name`` already exists.

        The reserved ``default`` profile can never be replaced by a
        prompt-altering profile: unconfigured agents resolve it, so allowing an
        override would change prompts for callers who never opted in.
        """
        if not isinstance(profile, PromptProfile):
            raise TypeError("profile must be a PromptProfile instance")
        if name == DEFAULT_PROFILE_NAME and not profile.is_prompt_neutral:
            raise ValueError(
                "The reserved 'default' profile must stay prompt-neutral "
                "(no system_prompt_prefix/suffix); it is applied to agents "
                "that never opted in, so overriding its prompt would break "
                "backward compatibility."
            )
        with self._lock:
            if not override and name in self._profiles:
                raise ValueError(f"Profile '{name}' is already registered")
            self._profiles[name] = profile

    def resolve(self, name: Optional[str] = None, require: bool = False) -> PromptProfile:
        """Resolve a profile by name.

        Falls back to the behaviour-neutral ``default`` profile when no match is
        found. When ``require`` is True and ``name`` does not match a registered
        profile, a ``KeyError`` is raised instead — so an explicitly-configured
        profile name with a typo surfaces to the caller rather than being
        silently dropped.
        """
        with self._lock:
            if name:
                profile = self._profiles.get(name)
                if profile is not None:
                    return profile
                if require:
                    raise KeyError(
                        f"Prompt profile '{name}' is not registered; "
                        f"available profiles: {sorted(self._profiles)}"
                    )
            return self._profiles[DEFAULT_PROFILE_NAME]

    def list_profiles(self) -> List[str]:
        """List all registered profile names."""
        with self._lock:
            return sorted(self._profiles.keys())

    def clear(self) -> None:
        """Reset to just the built-in ``default`` profile (primarily for tests)."""
        with self._lock:
            self._profiles = {
                DEFAULT_PROFILE_NAME: PromptProfile(name=DEFAULT_PROFILE_NAME),
            }


_global_registry = PromptProfileRegistry()


def register_profile(name: str, profile: PromptProfile, override: bool = True) -> None:
    """Register a prompt profile with the global registry."""
    _global_registry.register(name, profile, override=override)


def resolve_profile(name: Optional[str] = None, require: bool = False) -> PromptProfile:
    """Resolve a prompt profile by name from the global registry.

    With no matching profile this returns the ``default`` profile, whose
    ``apply_system_prompt`` is a pure no-op. Pass ``require=True`` to raise a
    ``KeyError`` when ``name`` is not registered (used for explicitly-configured
    profiles so typos fail loudly).
    """
    return _global_registry.resolve(name=name, require=require)


def list_profiles() -> List[str]:
    """List all registered prompt profile names."""
    return _global_registry.list_profiles()


def _discover_entry_point_profiles() -> None:
    """Discover third-party profiles via the entry-point group.

    Entry points in group ``praisonaiagents.prompt_profiles`` should load to a
    ``PromptProfile`` instance or a zero-arg factory returning one. Discovery
    is best-effort; individual plugin failures are logged at debug level and
    skipped so a broken plugin never breaks agent construction.
    """
    import logging
    try:
        from importlib.metadata import entry_points

        eps = entry_points(group="praisonaiagents.prompt_profiles")
    except Exception as e:  # entry_points unavailable or errored
        logging.debug("Prompt profile entry-point discovery skipped: %s", e)
        return

    for ep in eps:
        try:
            # Never let a plugin silently override the behaviour-neutral
            # ``default`` profile: unconfigured agents resolve it, so overriding
            # it would change prompts for users who never opted in.
            if ep.name == DEFAULT_PROFILE_NAME:
                continue
            obj = ep.load()
            profile = obj() if callable(obj) and not isinstance(obj, PromptProfile) else obj
            if isinstance(profile, PromptProfile):
                _global_registry.register(ep.name, profile)
        except Exception as e:
            logging.debug("Prompt profile plugin '%s' failed to load: %s", ep.name, e)
            continue


_discover_entry_point_profiles()
