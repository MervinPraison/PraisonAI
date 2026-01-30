# Suppress crewai.cli.config logger BEFORE any imports to prevent INFO log
import logging
logging.getLogger('crewai.cli.config').setLevel(logging.ERROR)

# Disable OpenTelemetry SDK
import os
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["EC_TELEMETRY"] = "false"

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
    'AgentApp',  # Production deployment platform (v0.14.16+)
    'recipe',
    'embed',
    'embedding',
]


# Lazy loading for heavy imports
def __getattr__(name):
    """Lazy load heavy modules to improve import time."""
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
    elif name == 'AgentApp':
        from .app import AgentApp
        return AgentApp
    
    # Try praisonaiagents exports
    try:
        import praisonaiagents
        if hasattr(praisonaiagents, name):
            return getattr(praisonaiagents, name)
    except ImportError:
        pass
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")



