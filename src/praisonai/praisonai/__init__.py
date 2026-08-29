import threading

from ._bootstrap import ensure_praisonai_code

ensure_praisonai_code()

# Version is lightweight, import directly
from .version import __version__

# Define __all__ for lazy loading
__all__ = [
    'PraisonAI',
    'run',
    'arun',
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
    # Integration functions
    'run_integrated_gateway',
]

# Telemetry initialization state - thread-safe (threading imported above)
_telemetry_lock = threading.Lock()
_telemetry_initialized = False

def _get_telemetry_defaults() -> dict[str, str]:
    """Get telemetry environment defaults without mutating os.environ.
    
    Returns:
        Dict of environment variable defaults for telemetry
    """
    import os
    defaults = {}
    
    # Respect any value the user already set
    if "OTEL_SDK_DISABLED" not in os.environ:
        langfuse_configured = bool(
            os.getenv("LANGFUSE_PUBLIC_KEY")
            or os.path.exists(os.path.expanduser("~/.praisonai/langfuse.env"))
        )
        defaults["OTEL_SDK_DISABLED"] = "false" if langfuse_configured else "true"
    
    if "EC_TELEMETRY" not in os.environ:
        defaults["EC_TELEMETRY"] = "false"
    
    return defaults


def _ensure_telemetry_defaults() -> None:
    """Apply telemetry env defaults exactly once, on first observability use.
    
    Thread-safe implementation using double-checked locking pattern.
    DEPRECATED: Use _apply_telemetry_defaults() with explicit config instead.
    """
    global _telemetry_initialized
    if _telemetry_initialized:  # fast path, OK without lock
        return
    with _telemetry_lock:
        if _telemetry_initialized:
            return
        _apply_telemetry_defaults(_get_telemetry_defaults())
        _telemetry_initialized = True


def _apply_telemetry_defaults(env_vars: dict[str, str]) -> None:
    """Apply telemetry defaults to os.environ.
    
    Args:
        env_vars: Dict of environment variables to set
    """
    import os
    for key, value in env_vars.items():
        os.environ.setdefault(key, value)


# Cached broken-install ImportError from praisonaiagents so repeated attribute
# lookups surface the real root cause without re-attempting the failing import.
_praisonaiagents_import_error = None


# Lazy loading for heavy imports
def __getattr__(name):
    """Lazy load heavy modules to improve import time."""
    # Note: Telemetry initialization moved out of lazy hook to avoid side effects
    # It should be called explicitly from cli.PraisonAI.__init__ instead

    if name == 'run':
        from ._entrypoint import run
        return run
    elif name == 'arun':
        from ._entrypoint import arun
        return arun
    elif name == 'PraisonAI':
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
    elif name == 'build_host_app':
        from .integration.host_app import build_host_app
        return build_host_app
    elif name == 'configure_host':
        from .integration.host_app import configure_host
        return configure_host
    elif name == 'run_integrated_gateway':
        from .integration.gateway_host import run_integrated_gateway
        return run_integrated_gateway
    elif name in ('AgentOS', 'AgentApp'):
        # AgentApp is a silent alias for AgentOS (backward compatibility)
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
        # Route through ``praisonai.db`` (not ``db.adapter`` directly) so the
        # deprecation warning defined on the ``praisonai.db`` import path fires
        # consistently. ``db`` classes are deprecated in favour of the ``db(...)``
        # factory; ``from praisonai import DB`` must warn just like
        # ``from praisonai.db import DB``.
        from . import db as _db
        return getattr(_db, name)
    # Note: n8n is available via direct import: from praisonai.n8n import YAMLToN8nConverter
    # Lazy loading from main package causes recursion, so use direct import for now
    
    # Try praisonaiagents exports. Distinguish "not installed" (ModuleNotFoundError
    # -> genuine attribute miss) from "installed but failed to import partway"
    # (ImportError, e.g. a transitive dep version conflict). The latter is the most
    # common source of new-installer confusion: silently swallowing it turns a real
    # broken-install error into a misleading "has no attribute" hunt. Cache the
    # broken-install failure so repeated lookups don't re-pay the import cost.
    global _praisonaiagents_import_error
    if _praisonaiagents_import_error is not None:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}: praisonaiagents is "
            f"installed but failed to import ({_praisonaiagents_import_error})"
        ) from _praisonaiagents_import_error

    try:
        import praisonaiagents
    except ModuleNotFoundError as e:
        if e.name == "praisonaiagents":
            # Genuinely not installed — this is a real attribute miss.
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
        # praisonaiagents IS installed but a transitive dep is missing.
        # Surface the real cause instead of a misleading attribute error.
        _praisonaiagents_import_error = e
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}: praisonaiagents is "
            f"installed but failed to import ({e})"
        ) from e
    except ImportError as e:
        _praisonaiagents_import_error = e
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}: praisonaiagents is "
            f"installed but failed to import ({e})"
        ) from e

    if hasattr(praisonaiagents, name):
        return getattr(praisonaiagents, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")



