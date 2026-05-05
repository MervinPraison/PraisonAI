import threading

# Version is lightweight, import directly
from .version import __version__

# Define __all__ for lazy loading
__all__ = [
    'PraisonAI',
    '__version__',
    'Deploy',
    'DeployConfig',
    'DeployType',
    'CloudProvider',
    'AgentOS',  # Production deployment platform (v0.14.16+)
    'AgentApp',  # Silent alias for AgentOS (backward compat)
    'Agent',  # Wrapper Agent with CLI backend string resolution
    'recipe',
    'embed',
    'embedding',
    'DB',  # Short alias for PraisonAIDB — recommended for simplicity
    'ManagedAgent',
    'ManagedConfig',
    'AnthropicManagedAgent',
    'LocalManagedAgent',          # backward compat alias
    'LocalManagedConfig',         # backward compat alias
    'SandboxedAgent',             # new honest name
    'SandboxedAgentConfig',       # new honest name
    # New canonical agent backends
    'HostedAgent',
    'HostedAgentConfig', 
    'LocalAgent',
    'LocalAgentConfig',
]

# Telemetry initialization state - thread-safe (threading imported above)
_telemetry_lock = threading.Lock()
_telemetry_initialized = False

def _ensure_telemetry_defaults() -> None:
    """Apply telemetry env defaults exactly once, on first observability use.
    
    Thread-safe implementation using double-checked locking pattern.
    """
    global _telemetry_initialized
    if _telemetry_initialized:  # fast path, OK without lock
        return
    with _telemetry_lock:
        if _telemetry_initialized:
            return
        import os
        # Respect any value the user already set
        if "OTEL_SDK_DISABLED" not in os.environ:
            langfuse_configured = bool(
                os.getenv("LANGFUSE_PUBLIC_KEY")
                or os.path.exists(os.path.expanduser("~/.praisonai/langfuse.env"))
            )
            os.environ["OTEL_SDK_DISABLED"] = "false" if langfuse_configured else "true"
        os.environ.setdefault("EC_TELEMETRY", "false")  # respect user overrides
        _telemetry_initialized = True


# Lazy loading for heavy imports
def __getattr__(name):
    """Lazy load heavy modules to improve import time."""
    # Note: Telemetry initialization moved out of lazy hook to avoid side effects
    # It should be called explicitly from cli.PraisonAI.__init__ instead

    if name == 'PraisonAI':
        from .cli import PraisonAI
        return PraisonAI
    elif name == 'Agent':
        from .agent import Agent
        return Agent
    elif name == 'Deploy':
        from .deploy import Deploy
        return Deploy
    elif name == 'DeployConfig':
        from .deploy import DeployConfig
        return DeployConfig
    elif name == 'DeployType':
        from .deploy import DeployType
        return DeployType
    elif name == 'CloudProvider':
        from .deploy import CloudProvider
        return CloudProvider
    elif name == 'recipe':
        from .recipe import core as recipe_module
        return recipe_module
    elif name == 'embed':
        # Re-export from core SDK for unified API
        from praisonaiagents.embedding.embed import embed
        return embed
    elif name == 'embedding':
        # Re-export from core SDK for unified API
        from praisonaiagents.embedding.embed import embedding
        return embedding
    elif name == 'aembed':
        from praisonaiagents.embedding.embed import aembed
        return aembed
    elif name == 'aembedding':
        from praisonaiagents.embedding.embed import aembedding
        return aembedding
    elif name == 'EmbeddingResult':
        from praisonaiagents.embedding import EmbeddingResult
        return EmbeddingResult
    elif name == 'AgentOS':
        from .app import AgentOS
        return AgentOS
    elif name == 'AgentApp':
        # Silent alias for AgentOS (backward compatibility)
        from .app import AgentOS
        return AgentOS
    elif name in ('ManagedAgent', 'ManagedAgentIntegration'):
        from .integrations.managed_agents import ManagedAgent
        return ManagedAgent
    elif name == 'AnthropicManagedAgent':
        from .integrations.managed_agents import AnthropicManagedAgent
        return AnthropicManagedAgent
    elif name == 'LocalManagedAgent':
        from .integrations.managed_local import LocalManagedAgent
        return LocalManagedAgent
    elif name == 'LocalManagedConfig':
        from .integrations.managed_local import LocalManagedConfig
        return LocalManagedConfig
    elif name == 'SandboxedAgent':
        from .integrations.sandboxed_agent import SandboxedAgent
        return SandboxedAgent
    elif name == 'SandboxedAgentConfig':
        from .integrations.sandboxed_agent import SandboxedAgentConfig
        return SandboxedAgentConfig
    elif name in ('ManagedConfig', 'ManagedBackendConfig'):
        from .integrations.managed_agents import ManagedConfig
        return ManagedConfig
    # New canonical agent backends
    elif name == 'HostedAgent':
        from .integrations.hosted_agent import HostedAgent
        return HostedAgent
    elif name == 'HostedAgentConfig':
        from .integrations.hosted_agent import HostedAgentConfig
        return HostedAgentConfig
    elif name == 'LocalAgent':
        from .integrations.local_agent import LocalAgent
        return LocalAgent
    elif name == 'LocalAgentConfig':
        from .integrations.local_agent import LocalAgentConfig
        return LocalAgentConfig
    elif name in ('DB', 'PraisonAIDB', 'PraisonDB'):
        from .db.adapter import DB
        return DB
    # Note: n8n is available via direct import: from praisonai.n8n import YAMLToN8nConverter
    # Lazy loading from main package causes recursion, so use direct import for now
    
    # Try praisonaiagents exports
    try:
        import praisonaiagents
        if hasattr(praisonaiagents, name):
            return getattr(praisonaiagents, name)
    except ImportError:
        pass
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")



