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


def _webhook_loader():
    return _load_bot_class("webhook", "WebhookBot")


def _signal_loader():
    return _load_bot_class("signal", "SignalBot")


def _local_loader():
    return _load_bot_class("local", "LocalBot")

# Built-in bot platforms with lazy loading
_BUILTIN_PLATFORMS = {
    "telegram": _telegram_loader,
    "discord": _discord_loader,
    "slack": _slack_loader,
    "whatsapp": _whatsapp_loader,
    "linear": _linear_loader,
    "email": _email_loader,
    "agentmail": _agentmail_loader,
    "webhook": _webhook_loader,
    "signal": _signal_loader,
    "local": _local_loader,
}

# Credential env var(s) that identify a present, ready-to-use platform token
# (Issue #4779). This is the single in-tree source of truth for built-in
# platforms — the same mapping the onboarding wizard hard-codes — so the
# gateway can auto-enable a channel from a present credential with no
# ``channels:`` block. The first entry is the primary token used to seed the
# auto-filled channel's ``token: ${ENV}`` reference; any further entries are
# additional required credentials that must all be present. Plugin channels
# self-describe theirs via their ``ChannelDescriptor`` (see
# ``get_platform_credential_env``), so this only lists built-ins.
_BUILTIN_CREDENTIAL_ENV: Dict[str, tuple] = {
    "telegram": ("TELEGRAM_BOT_TOKEN",),
    "discord": ("DISCORD_BOT_TOKEN",),
    "slack": ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"),
    "whatsapp": ("WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID"),
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
        # Zero-code drop-in channels (Issue #4104): a single-file adapter placed
        # in ``./.praisonai/channels/`` or ``~/.praisonai/channels/`` is picked
        # up under the same trust model as single-file plugins, so a custom
        # platform works from the CLI with no install step. Best-effort — never
        # blocks registry construction.
        self._discover_channel_files()

    def _discover_channel_files(self) -> None:
        """Load single-file channel adapters from the drop-in directories.

        Mirrors ``praisonaiagents.plugins.discovery``: project-local files are
        gated behind the ``PRAISONAI_ALLOW_PROJECT_PLUGINS`` trust flag,
        user-global files are trusted. Each ``.py`` file is imported and every
        ``BasePlatformAdapter`` subclass it defines is registered under its
        declared ``platform_name`` (falling back to the file stem).
        """
        import logging

        logger = logging.getLogger(__name__)
        try:
            for path in self._discover_channel_file_paths():
                try:
                    self._load_channel_file(path)
                except Exception:
                    logger.debug("Skipping invalid channel file %s", path, exc_info=True)
        except Exception:
            logger.debug("Channel drop-in discovery unavailable", exc_info=True)

    @staticmethod
    def _discover_channel_file_paths() -> "List[Any]":
        """Return channel drop-in ``.py`` paths in precedence order.

        Project: ``./.praisonai/channels/`` then user: ``~/.praisonai/channels/``.
        """
        try:
            from praisonaiagents.paths import (
                get_plugins_dir,
                get_project_data_dir,
            )
        except Exception:
            return []

        dirs = []
        try:
            project_channels = get_project_data_dir() / "channels"
            if project_channels.is_dir():
                dirs.append(project_channels)
        except Exception:
            pass
        try:
            # ``get_plugins_dir()`` is ``~/.praisonai/plugins``; its parent is
            # the user ``~/.praisonai`` home, so drop-ins live alongside plugins.
            user_channels = get_plugins_dir().parent / "channels"
            if user_channels.is_dir():
                dirs.append(user_channels)
        except Exception:
            pass

        paths = []
        for d in dirs:
            try:
                for item in sorted(d.iterdir()):
                    if item.suffix == ".py" and not item.name.startswith("_"):
                        paths.append(item)
            except Exception:
                continue
        return paths

    @staticmethod
    def _is_project_local_channel(path) -> bool:
        """True when ``path`` is reached via ``./.praisonai/channels/``.

        The trust gate must fire on *how the file was reached*, not on where a
        symlink ultimately points — a repository-controlled
        ``.praisonai/channels/evil.py -> /tmp/evil.py`` is still
        project-controlled code. Mirrors ``plugins.discovery._is_project_local``
        but scoped to the *channels* directory: resolve only the parent dirs
        (so a symlinked ``channels`` dir is still recognised) while keeping the
        file's own name un-resolved (so a symlinked file cannot slip the gate).
        """
        try:
            from praisonaiagents.paths import get_project_data_dir

            project_channels = (get_project_data_dir() / "channels").resolve()
        except Exception:
            return False
        try:
            located = path.expanduser()
            candidate = located.parent.resolve() / located.name
            candidate.relative_to(project_channels)
            return True
        except Exception:
            return False

    def _load_channel_file(self, path) -> None:
        """Import one channel drop-in file and register its adapter classes.

        Project-local files are gated behind ``PRAISONAI_ALLOW_PROJECT_PLUGINS``
        (see ``_is_project_local_channel``) so a cloned repo cannot silently run
        a malicious drop-in adapter until the user opts in.
        """
        import importlib.util
        import inspect
        import logging
        import sys

        logger = logging.getLogger(__name__)

        # Trust gate: project-local drop-ins share the single-file plugin
        # opt-in flag; user-global drop-ins are trusted. NOTE: the plugins
        # helper ``_is_project_local`` is scoped to ``.praisonai/plugins`` and
        # would wrongly classify a ``.praisonai/channels`` file as non-project,
        # so we compute project-locality against the *channels* directory here
        # (reusing only the shared env-flag helper).
        try:
            from praisonaiagents.plugins.discovery import _project_plugins_allowed

            if self._is_project_local_channel(path) and not _project_plugins_allowed():
                logger.warning(
                    "Refusing to load project channel %s: set "
                    "PRAISONAI_ALLOW_PROJECT_PLUGINS=true to enable.",
                    path,
                )
                return
        except Exception:
            logger.debug("Channel trust gate unavailable", exc_info=True)

        try:
            from praisonaiagents.bots import BasePlatformAdapter
        except Exception:
            return

        module_name = f"praison_channel_{path.stem}_{id(path)}"
        spec = importlib.util.spec_from_file_location(module_name, str(path))
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj is BasePlatformAdapter or not issubclass(obj, BasePlatformAdapter):
                continue
            if obj.__module__ != module_name:
                continue
            name = getattr(obj, "platform_name", None) or path.stem
            descriptor = None
            candidate = getattr(obj, "channel_descriptor", None)
            if candidate is not None:
                try:
                    descriptor = candidate() if callable(candidate) else candidate
                except Exception:
                    descriptor = None
            self.register_with_capabilities(
                str(name).lower(), obj, descriptor=descriptor
            )

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


def get_platform_credential_env(name: str) -> tuple:
    """Return the credential env var(s) that identify a present token (#4779).

    Single source of truth for credential-presence auto-enablement. Built-in
    platforms come from ``_BUILTIN_CREDENTIAL_ENV`` (the same mapping the
    onboarding wizard uses); plugin/entry-point channels self-describe theirs
    via their ``ChannelDescriptor``'s ``config_fields``.

    A plugin channel is only auto-enable-able when **every** ``required`` field
    it declares can be sourced from the environment (i.e. declares an ``env``
    fallback). If any required field lacks an ``env`` fallback, the channel
    could not be brought up from env vars alone — auto-enabling it would seed a
    channel that ``apply_channel_descriptor`` then rejects for the missing
    required field, aborting the whole gateway. In that case we return ``()``
    so the platform is left for explicit configuration. When there are no
    required fields, an env-backed ``secret`` field is sufficient to identify a
    ready-to-use credential. All returned vars must be present for the channel
    to be auto-enabled.

    Args:
        name: Platform identifier.

    Returns:
        A tuple of env-var names (empty when the platform declares none, or
        when a required field cannot be sourced from the environment).
    """
    key = name.lower()
    builtin = _BUILTIN_CREDENTIAL_ENV.get(key)
    if builtin:
        return builtin
    descriptor = get_platform_descriptor(key)
    if descriptor is None:
        return ()
    fields = getattr(descriptor, "config_fields", None) or []
    required_fields = [spec for spec in fields if getattr(spec, "required", False)]
    if required_fields:
        # Every required field must be env-sourceable, otherwise the channel
        # cannot be auto-enabled from the environment alone — return () so the
        # platform is left for explicit config instead of failing at startup.
        required_env = tuple(
            env
            for spec in required_fields
            if (env := getattr(spec, "env", None))
        )
        if len(required_env) != len(required_fields):
            return ()
        return required_env
    secret = tuple(
        env
        for spec in fields
        if getattr(spec, "secret", False)
        and (env := getattr(spec, "env", None))
    )
    return secret


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
