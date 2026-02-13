"""
Platform registry for PraisonAI BotOS.

Maps platform names to their bot adapter classes (lazy-loaded).
Extensible: third-party platforms can register via ``register_platform()``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Type

# Lazy references: (module_path, class_name)
_BUILTIN_PLATFORMS: Dict[str, tuple] = {
    "telegram": ("praisonai.bots.telegram", "TelegramBot"),
    "discord": ("praisonai.bots.discord", "DiscordBot"),
    "slack": ("praisonai.bots.slack", "SlackBot"),
    "whatsapp": ("praisonai.bots.whatsapp", "WhatsAppBot"),
}

# Custom platforms registered at runtime
_custom_platforms: Dict[str, Any] = {}


def get_platform_registry() -> Dict[str, Any]:
    """Return the combined registry of all known platforms.

    Keys are platform names, values are either:
    - A class (custom platforms, already resolved)
    - A (module, classname) tuple (builtins, lazy-resolved on use)
    """
    combined: Dict[str, Any] = {}
    combined.update(_BUILTIN_PLATFORMS)
    combined.update(_custom_platforms)
    return combined


def register_platform(name: str, adapter_class: Type) -> None:
    """Register a custom platform adapter.

    Args:
        name: Platform identifier (lowercase).
        adapter_class: The bot adapter class.
    """
    _custom_platforms[name.lower()] = adapter_class


def list_platforms() -> List[str]:
    """List all registered platform names."""
    return sorted(set(list(_BUILTIN_PLATFORMS.keys()) + list(_custom_platforms.keys())))


def resolve_adapter(name: str) -> Type:
    """Resolve a platform name to its adapter class (lazy import).

    Args:
        name: Platform identifier.

    Returns:
        The adapter class.

    Raises:
        ValueError: If the platform is not registered.
    """
    key = name.lower()

    # Custom platforms are already classes
    if key in _custom_platforms:
        cls = _custom_platforms[key]
        if isinstance(cls, type):
            return cls

    # Builtins are lazy (module, classname) tuples
    if key in _BUILTIN_PLATFORMS:
        ref = _BUILTIN_PLATFORMS[key]
        if isinstance(ref, tuple):
            module_path, class_name = ref
            import importlib
            mod = importlib.import_module(module_path)
            return getattr(mod, class_name)

    raise ValueError(
        f"Unknown platform: {name!r}. "
        f"Available: {', '.join(list_platforms())}"
    )
