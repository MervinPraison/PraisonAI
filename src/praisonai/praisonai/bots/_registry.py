"""
Platform registry for PraisonAI BotOS.

Maps platform names to their bot adapter classes (lazy-loaded).
Extensible: third-party platforms can register via ``register_platform()``.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Type, Optional

from .._registry import PluginRegistry


def _telegram_loader():
    import importlib
    mod = importlib.import_module("praisonai.bots.telegram")
    return getattr(mod, "TelegramBot")

def _discord_loader():
    import importlib
    mod = importlib.import_module("praisonai.bots.discord")
    return getattr(mod, "DiscordBot")

def _slack_loader():
    import importlib
    mod = importlib.import_module("praisonai.bots.slack")
    return getattr(mod, "SlackBot")

def _whatsapp_loader():
    import importlib
    mod = importlib.import_module("praisonai.bots.whatsapp")
    return getattr(mod, "WhatsAppBot")

def _linear_loader():
    import importlib
    mod = importlib.import_module("praisonai.bots.linear")
    return getattr(mod, "LinearBot")

def _email_loader():
    import importlib
    mod = importlib.import_module("praisonai.bots.email")
    return getattr(mod, "EmailBot")

def _agentmail_loader():
    import importlib
    mod = importlib.import_module("praisonai.bots.agentmail")
    return getattr(mod, "AgentMailBot")

# Built-in bot platforms with lazy loading
_BUILTIN_PLATFORMS = {
    "telegram": _telegram_loader,
    "discord": _discord_loader,
    "slack": _slack_loader,
    "whatsapp": _whatsapp_loader,
    "linear": _linear_loader,
    "email": _email_loader,
    "agentmail": _agentmail_loader,
}


class BotPlatformRegistry(PluginRegistry):
    """Registry for bot platform adapters."""
    
    def __init__(self):
        super().__init__(
            entry_point_group="praisonai.bots",
            builtins=_BUILTIN_PLATFORMS
        )


# Default registry (lazy, module-private)
_default_registry: Optional[BotPlatformRegistry] = None
_default_lock = threading.Lock()


def get_default_bot_registry() -> BotPlatformRegistry:
    """Return the process-default bot registry. Prefer DI; use this only at the edge.""" 
    global _default_registry
    if _default_registry is None:
        with _default_lock:
            if _default_registry is None:
                _default_registry = BotPlatformRegistry()
    return _default_registry


# Backward compatibility API
_bot_registry = get_default_bot_registry()


def get_platform_registry() -> Dict[str, Any]:
    """Return the combined registry of all known platforms.
    
    Backward compatibility function that returns a dict-like view.
    """
    # Return a simplified view for backward compatibility
    result = {}
    for name in _bot_registry.list_names():
        result[name] = name  # Simplified representation
    return result


def register_platform(name: str, adapter_class: Type) -> None:
    """Register a custom platform adapter.

    Args:
        name: Platform identifier (lowercase).
        adapter_class: The bot adapter class.
    """
    _bot_registry.register(name.lower(), adapter_class)


def list_platforms() -> List[str]:
    """List all registered platform names."""
    return _bot_registry.list_names()


def resolve_adapter(name: str) -> Type:
    """Resolve a platform name to its adapter class (lazy import).

    Args:
        name: Platform identifier.

    Returns:
        The adapter class.

    Raises:
        ValueError: If the platform is not registered.
    """
    return _bot_registry.resolve(name.lower())
