"""
Platform registry for PraisonAI BotOS.

Maps platform names to their bot adapter classes (lazy-loaded).
Extensible: third-party platforms can register via ``register_platform()``.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Type, Optional

from .._registry import PluginRegistry
from praisonaiagents.bots.protocols import ChannelDescriptor, PlatformCapabilities


def _load_bot_class(module: str, class_name: str):
    import importlib

    mod = importlib.import_module(f"praisonai_bot.bots.{module}")
    return getattr(mod, class_name)


def _telegram_loader():
    return _load_bot_class("telegram", "TelegramBot")


def _discord_loader():
    return _load_bot_class("discord", "DiscordBot")


def _slack_loader():
    return _load_bot_class("slack", "SlackBot")


def _whatsapp_loader():
    return _load_bot_class("whatsapp", "WhatsAppBot")


def _linear_loader():
    return _load_bot_class("linear", "LinearBot")


def _email_loader():
    return _load_bot_class("email", "EmailBot")


def _agentmail_loader():
    return _load_bot_class("agentmail", "AgentMailBot")

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
    """Registry for bot platform adapters with capability descriptors."""
    
    def __init__(self):
        super().__init__(
            entry_point_group="praisonai.channels",
            builtins=_BUILTIN_PLATFORMS,
            discover_entry_points=False,
        )
        # Store capabilities for each platform (initialised before entry-point
        # discovery so any future capability-aware discovery is safe).
        self._capabilities: Dict[str, PlatformCapabilities] = {}
        self._capabilities_lock = threading.Lock()
        # Store optional self-description descriptors (config fields, setup hook,
        # system-prompt hint) so config/onboarding/prompt can wire a channel
        # with zero core edits.
        self._descriptors: Dict[str, ChannelDescriptor] = {}
        self._descriptors_lock = threading.Lock()
        # Discover third-party channel connectors without shadowing builtins.
        self._discover_channel_entry_points()

    def _discover_channel_entry_points(self) -> None:
        """Discover channel connectors from the ``praisonai.channels`` group."""
        import logging
        from importlib.metadata import entry_points
        logger = logging.getLogger(__name__)
        # Names this package ships as builtins are also declared as entry points
        # (for external discoverability), so a duplicate here is expected and not
        # a conflict — log those at DEBUG and only warn for genuine third-party
        # shadowing attempts.
        builtin_names = set(_BUILTIN_PLATFORMS)
        try:
            for ep in entry_points(group="praisonai.channels"):
                # Do not let a third-party entry point silently shadow a
                # built-in (or already-registered) channel loader.
                if ep.name.lower() in self._loaders:
                    if ep.name.lower() in builtin_names:
                        logger.debug(
                            "Channel entry point %r matches a built-in loader; "
                            "keeping the built-in.", ep.name
                        )
                    else:
                        logger.warning(
                            "Skipping duplicate channel entry point %r; a loader "
                            "with that name is already registered.", ep.name
                        )
                    continue
                self._add_loader(ep.name, ep.load)
        except Exception:
            logger.debug(
                "Entry points not available for group praisonai.channels",
                exc_info=True,
            )
    
    def register_with_capabilities(
        self, 
        name: str, 
        adapter_class: Type,
        capabilities: Optional[PlatformCapabilities] = None,
        descriptor: Optional[ChannelDescriptor] = None,
    ) -> None:
        """Register a platform adapter with its capabilities.
        
        Args:
            name: Platform identifier (lowercase)
            adapter_class: The bot adapter class
            capabilities: Optional platform capabilities descriptor
            descriptor: Optional channel self-description (config fields, setup
                hook, system-prompt hint) so config/onboarding/prompt can wire
                the channel with zero core edits.
        """
        self.register(name.lower(), adapter_class)
        if capabilities:
            with self._capabilities_lock:
                self._capabilities[name.lower()] = capabilities
        if descriptor is not None:
            with self._descriptors_lock:
                self._descriptors[name.lower()] = descriptor
    
    def get_descriptor(self, name: str) -> Optional[ChannelDescriptor]:
        """Get the self-description descriptor for a platform, if any.
        
        Checks explicitly-registered descriptors first, then falls back to a
        ``channel_descriptor`` class attribute/method on the adapter class so a
        plugin can self-describe purely by declaring it on the adapter.
        
        Args:
            name: Platform identifier
            
        Returns:
            The channel descriptor, or None if the platform does not self-describe.
        """
        name = name.lower()
        with self._descriptors_lock:
            if name in self._descriptors:
                return self._descriptors[name]
        try:
            adapter_class = self.resolve(name)
        except (ValueError, AttributeError):
            return None
        candidate = getattr(adapter_class, "channel_descriptor", None)
        if candidate is None:
            return None
        try:
            descriptor = candidate() if callable(candidate) else candidate
        except Exception:
            return None
        if descriptor is not None:
            with self._descriptors_lock:
                self._descriptors[name] = descriptor
        return descriptor
    
    def get_capabilities(self, name: str) -> PlatformCapabilities:
        """Get capabilities for a platform.
        
        Args:
            name: Platform identifier
            
        Returns:
            Platform capabilities (defaults if not specified)
        """
        name = name.lower()
        
        # Check stored capabilities first
        with self._capabilities_lock:
            if name in self._capabilities:
                return self._capabilities[name]
        
        # Try to get from adapter class
        try:
            adapter_class = self.resolve(name)
            # Check if adapter has a default capabilities class method
            if hasattr(adapter_class, 'default_capabilities'):
                caps = adapter_class.default_capabilities()
                # Cache for future use
                with self._capabilities_lock:
                    self._capabilities[name] = caps
                return caps
        except (ValueError, AttributeError):
            pass
        
        # Return defaults
        return PlatformCapabilities()


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


# Backward compatibility API - lazy loading to preserve original behavior
_bot_registry = None

def _get_lazy_registry():
    """Get registry lazily to avoid eager loading at module import."""
    global _bot_registry
    if _bot_registry is None:
        _bot_registry = get_default_bot_registry()
    return _bot_registry


def get_platform_registry() -> Dict[str, Any]:
    """Return the combined registry of all known platforms.
    
    Backward compatibility function that returns original format:
    {name: class_or_tuple} to preserve external caller contracts.
    """
    registry = _get_lazy_registry()
    result = {}
    for name in registry.list_names():
        try:
            # Return the resolved class to maintain original API contract
            result[name] = registry.resolve(name)
        except ValueError:
            # Skip broken registrations
            pass
    return result


def register_platform(
    name: str, 
    adapter_class: Type,
    capabilities: Optional[PlatformCapabilities] = None,
    descriptor: Optional[ChannelDescriptor] = None,
) -> None:
    """Register a custom platform adapter with optional capabilities.

    Args:
        name: Platform identifier (lowercase).
        adapter_class: The bot adapter class.
        capabilities: Optional platform capabilities descriptor.
        descriptor: Optional channel self-description (config fields, setup
            hook, system-prompt hint). When provided, the channel's own config
            keys validate and reach the adapter, the onboarding wizard prompts
            for them, and the agent prompt gains the channel hint — with zero
            edits to the config schema, onboarding, or prompt builder.
    """
    registry = _get_lazy_registry()
    if isinstance(registry, BotPlatformRegistry):
        registry.register_with_capabilities(
            name.lower(), adapter_class, capabilities, descriptor
        )
    else:
        # Fallback for compatibility
        registry.register(name.lower(), adapter_class)


def list_platforms() -> List[str]:
    """List all registered platform names."""
    return _get_lazy_registry().list_names()


def resolve_adapter(name: str) -> Type:
    """Resolve a platform name to its adapter class (lazy import).

    Args:
        name: Platform identifier.

    Returns:
        The adapter class.

    Raises:
        ValueError: If the platform is not registered.
    """
    return _get_lazy_registry().resolve(name.lower())


def get_platform_capabilities(name: str) -> PlatformCapabilities:
    """Get capabilities for a platform.
    
    Args:
        name: Platform identifier.
        
    Returns:
        Platform capabilities descriptor.
    """
    registry = _get_lazy_registry()
    if isinstance(registry, BotPlatformRegistry):
        return registry.get_capabilities(name.lower())
    # Fallback to defaults
    return PlatformCapabilities()


def get_platform_descriptor(name: str) -> Optional[ChannelDescriptor]:
    """Get the self-description descriptor for a platform, if any.

    Args:
        name: Platform identifier.

    Returns:
        The channel descriptor (config fields, setup hook, system-prompt hint),
        or None if the platform does not self-describe.
    """
    registry = _get_lazy_registry()
    if isinstance(registry, BotPlatformRegistry):
        return registry.get_descriptor(name.lower())
    return None


def get_channel_system_prompt_hint(name: str) -> str:
    """Return the system-prompt hint a channel declares, or an empty string.

    The gateway prompt assembly injects this whenever the channel is active so
    the agent knows which platform it is replying on and its constraints (e.g.
    "You are replying on IRC: plain text only, one short line."). Built-in
    platforms without a descriptor return "" and are unaffected.

    Args:
        name: Platform identifier.

    Returns:
        The channel's ``system_prompt_hint``, or "" when not declared.
    """
    descriptor = get_platform_descriptor(name)
    if descriptor is None:
        return ""
    return getattr(descriptor, "system_prompt_hint", "") or ""
