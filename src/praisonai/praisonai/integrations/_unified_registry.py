"""
Unified registry for all integration types in PraisonAI.

This replaces the manual __getattr__ ladder with a data-driven registry approach,
supporting CLI tools, managed agents, framework adapters, and RAG components.
"""

from typing import Any, Callable, Dict
from .._registry import PluginRegistry


class IntegrationRegistry(PluginRegistry[Any]):
    """Registry for all integration types with lazy loading."""
    
    def __init__(self):
        super().__init__(entry_point_group="praisonai.integrations")
        self._loaders: Dict[str, Callable[[], Any]] = {}
        self._register_builtin_integrations()

    def register_lazy(
        self,
        name: str,
        loader: Callable[[], Any],
        *,
        aliases: list[str] | None = None,
    ) -> None:
        """Register a lazily loaded integration."""
        with self._lock:
            canonical_name = name.lower()
            self._loaders[canonical_name] = loader

            if aliases:
                for alias in aliases:
                    self._aliases[alias.lower()] = canonical_name

    def resolve(self, name: str) -> Any:
        """Resolve integration name with lazy loader materialization."""
        with self._lock:
            normalized_name = name.lower()
            canonical_name = self._aliases.get(normalized_name, normalized_name)

            item = self._items.get(canonical_name)
            if item is None:
                loader = self._loaders.get(canonical_name)
                if loader is not None:
                    item = loader()
                    self._items[canonical_name] = item

            if item is not None:
                return item

            available_snapshot = sorted(
                set(self._items.keys()) | set(self._loaders.keys()) | set(self._aliases.keys())
            )

        raise ValueError(
            f"Unknown {self._entry_point_group} plugin: {name!r}. "
            f"Available: {available_snapshot}"
        )
    
    def _register_builtin_integrations(self):
        """Register all built-in integrations with lazy loading."""

        # CLI Tools — canonical loaders shared with ExternalAgentRegistry so a
        # new backend only has to be registered in one place (_cli_loaders.py).
        from ._cli_loaders import CLASS_NAME_LOADERS

        _claude_code = CLASS_NAME_LOADERS["ClaudeCodeIntegration"]
        _gemini_cli = CLASS_NAME_LOADERS["GeminiCLIIntegration"]
        _codex_cli = CLASS_NAME_LOADERS["CodexCLIIntegration"]
        _cursor_cli = CLASS_NAME_LOADERS["CursorCLIIntegration"]

        # Base classes
        def _base_cli_integration():
            from .base import BaseCLIIntegration
            return BaseCLIIntegration
        
        def _cli_execution_error():
            from .base import CLIExecutionError
            return CLIExecutionError
        
        # Managed agents  
        def _managed_agent():
            from .managed_agents import ManagedAgent
            return ManagedAgent
        
        def _anthropic_managed_agent():
            from .managed_agents import AnthropicManagedAgent
            return AnthropicManagedAgent
            
        def _managed_config():
            from .managed_agents import ManagedConfig
            return ManagedConfig
        
        # Local agents
        def _local_managed_agent():
            from .managed_local import LocalManagedAgent
            return LocalManagedAgent
            
        def _local_managed_config():
            from .managed_local import LocalManagedConfig
            return LocalManagedConfig
        
        # Sandboxed agents
        def _sandboxed_agent():
            from .sandboxed_agent import SandboxedAgent
            return SandboxedAgent
            
        def _sandboxed_agent_config():
            from .sandboxed_agent import SandboxedAgentConfig
            return SandboxedAgentConfig
        
        # Canonical agent backends
        def _hosted_agent():
            from .hosted_agent import HostedAgent
            return HostedAgent
            
        def _hosted_agent_config():
            from .hosted_agent import HostedAgentConfig
            return HostedAgentConfig
            
        def _local_agent():
            from .local_agent import LocalAgent
            return LocalAgent
            
        def _local_agent_config():
            from .local_agent import LocalAgentConfig
            return LocalAgentConfig
        
        # Registry functions
        def _get_available_integrations():
            from .base import get_available_integrations
            return get_available_integrations
            
        def _external_agent_registry():
            from .registry import ExternalAgentRegistry
            return ExternalAgentRegistry
            
        def _get_registry():
            from .registry import get_registry
            return get_registry
            
        def _register_integration():
            from .registry import register_integration
            return register_integration
            
        def _create_integration():
            from .registry import create_integration
            return create_integration
        
        # Register all with appropriate aliases
        self.register_lazy("BaseCLIIntegration", _base_cli_integration)
        self.register_lazy("CLIExecutionError", _cli_execution_error)
        
        self.register_lazy("ClaudeCodeIntegration", _claude_code)
        self.register_lazy("GeminiCLIIntegration", _gemini_cli)
        self.register_lazy("CodexCLIIntegration", _codex_cli)
        self.register_lazy("CursorCLIIntegration", _cursor_cli)
        
        self.register_lazy("ManagedAgent", _managed_agent, 
                     aliases=["ManagedAgentIntegration"])
        self.register_lazy("AnthropicManagedAgent", _anthropic_managed_agent)
        self.register_lazy("ManagedConfig", _managed_config,
                     aliases=["ManagedBackendConfig"])
        
        self.register_lazy("LocalManagedAgent", _local_managed_agent)
        self.register_lazy("LocalManagedConfig", _local_managed_config)
        
        self.register_lazy("SandboxedAgent", _sandboxed_agent)
        self.register_lazy("SandboxedAgentConfig", _sandboxed_agent_config)
        
        self.register_lazy("HostedAgent", _hosted_agent)
        self.register_lazy("HostedAgentConfig", _hosted_agent_config)
        self.register_lazy("LocalAgent", _local_agent)
        self.register_lazy("LocalAgentConfig", _local_agent_config)
        
        self.register_lazy("get_available_integrations", _get_available_integrations)
        self.register_lazy("ExternalAgentRegistry", _external_agent_registry)
        self.register_lazy("get_registry", _get_registry)
        self.register_lazy("register_integration", _register_integration)
        self.register_lazy("create_integration", _create_integration)


# Global registry instance — lazily constructed on first access instead of at
# import time. Constructing at module top violated the "no heavy module-level
# work" rule and paid the entry-point discovery cost even when the registry was
# never used. ``get_integrations_registry()`` is the preferred accessor; the
# historical ``INTEGRATIONS_REGISTRY`` name is preserved via module __getattr__.
import threading as _threading

_registry_instance: "IntegrationRegistry | None" = None
_registry_lock = _threading.Lock()


def get_integrations_registry() -> "IntegrationRegistry":
    """Return the process-default integration registry, building it lazily."""
    global _registry_instance
    if _registry_instance is None:
        with _registry_lock:
            if _registry_instance is None:
                _registry_instance = IntegrationRegistry()
    return _registry_instance


def __getattr__(name: str) -> Any:
    if name == "INTEGRATIONS_REGISTRY":
        return get_integrations_registry()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")