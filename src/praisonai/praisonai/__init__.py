# Suppress crewai.cli.config logger BEFORE any imports to prevent INFO log
import logging
logging.getLogger('crewai.cli.config').setLevel(logging.ERROR)

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
    'recipe',
    'embed',
    'embedding',
    'DB',  # Short alias for PraisonAIDB — recommended for simplicity
    'ManagedAgent',
    'ManagedConfig',
    'AnthropicManagedAgent',
    'LocalManagedAgent',
    'LocalManagedConfig',
    'SandboxedAgent',
    'SandboxedAgentConfig', 
    'E2BManagedAgent',
    'ModalManagedAgent',
]

# Telemetry initialization state
_telemetry_initialized = False

def _ensure_telemetry_defaults() -> None:
    """Apply telemetry env defaults exactly once, on first observability use."""
    global _telemetry_initialized
    if _telemetry_initialized:
        return
    import os
    langfuse_configured = bool(
        os.getenv("LANGFUSE_PUBLIC_KEY")
        or os.path.exists(os.path.expanduser("~/.praisonai/langfuse.env"))
    )
    if langfuse_configured:
        # Explicitly enable OTEL for Langfuse integration
        os.environ["OTEL_SDK_DISABLED"] = "false"
    else:
        os.environ.setdefault("OTEL_SDK_DISABLED", "true")
    os.environ.setdefault("EC_TELEMETRY", "false")  # respect user overrides
    _telemetry_initialized = True


# Lazy loading for heavy imports
def __getattr__(name):
    """Lazy load heavy modules to improve import time."""
    # Ensure telemetry defaults before any lazy import that may touch OTEL.
    _ensure_telemetry_defaults()

    if name == 'PraisonAI':
        from .cli import PraisonAI
        return PraisonAI
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
        from .integrations.managed_local import SandboxedAgent
        return SandboxedAgent
    elif name == 'SandboxedAgentConfig':
        from .integrations.managed_local import SandboxedAgentConfig
        return SandboxedAgentConfig
    elif name == 'E2BManagedAgent':
        from .integrations.managed_e2b import E2BManagedAgent
        return E2BManagedAgent
    elif name == 'ModalManagedAgent':
        from .integrations.managed_modal import ModalManagedAgent
        return ModalManagedAgent
    elif name in ('ManagedConfig', 'ManagedBackendConfig'):
        from .integrations.managed_agents import ManagedConfig
        return ManagedConfig
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



