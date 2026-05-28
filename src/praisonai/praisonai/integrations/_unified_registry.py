"""
Unified registry for all integration types in PraisonAI.

This replaces the manual __getattr__ ladder with a data-driven registry approach,
supporting CLI tools, managed agents, framework adapters, and RAG components.
"""

from typing import Any, Callable, Dict, Optional
from .._registry import PluginRegistry


class IntegrationRegistry(PluginRegistry[Any]):
    """Registry for all integration types with lazy loading."""
    
    def __init__(self):
        super().__init__(entry_point_group="praisonai.integrations")
        self._register_builtin_integrations()
    
    def _register_builtin_integrations(self):
        """Register all built-in integrations with lazy loading."""
        
        # CLI Tools
        def _claude_code():
            from .claude_code import ClaudeCodeIntegration
            return ClaudeCodeIntegration
            
        def _gemini_cli():
            from .gemini_cli import GeminiCLIIntegration
            return GeminiCLIIntegration
            
        def _codex_cli():
            from .codex_cli import CodexCLIIntegration
            return CodexCLIIntegration
            
        def _cursor_cli():
            from .cursor_cli import CursorCLIIntegration
            return CursorCLIIntegration
        
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
        self.register("BaseCLIIntegration", _base_cli_integration)
        self.register("CLIExecutionError", _cli_execution_error)
        
        self.register("ClaudeCodeIntegration", _claude_code)
        self.register("GeminiCLIIntegration", _gemini_cli)
        self.register("CodexCLIIntegration", _codex_cli)
        self.register("CursorCLIIntegration", _cursor_cli)
        
        self.register("ManagedAgent", _managed_agent, 
                     aliases=["ManagedAgentIntegration"])
        self.register("AnthropicManagedAgent", _anthropic_managed_agent)
        self.register("ManagedConfig", _managed_config,
                     aliases=["ManagedBackendConfig"])
        
        self.register("LocalManagedAgent", _local_managed_agent)
        self.register("LocalManagedConfig", _local_managed_config)
        
        self.register("SandboxedAgent", _sandboxed_agent)
        self.register("SandboxedAgentConfig", _sandboxed_agent_config)
        
        self.register("HostedAgent", _hosted_agent)
        self.register("HostedAgentConfig", _hosted_agent_config)
        self.register("LocalAgent", _local_agent)
        self.register("LocalAgentConfig", _local_agent_config)
        
        self.register("get_available_integrations", _get_available_integrations)
        self.register("ExternalAgentRegistry", _external_agent_registry)
        self.register("get_registry", _get_registry)
        self.register("register_integration", _register_integration)
        self.register("create_integration", _create_integration)


# Global registry instance
INTEGRATIONS_REGISTRY = IntegrationRegistry()