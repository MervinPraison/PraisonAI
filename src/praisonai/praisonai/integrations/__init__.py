"""
PraisonAI Integrations - External CLI tool and managed agent integrations.

This module provides integrations with external AI coding tools:
- Claude Code CLI
- Gemini CLI
- OpenAI Codex CLI
- Cursor CLI
- Managed Agent Backends (Anthropic Managed Agents API)

All integrations use lazy loading to avoid performance impact.

Usage:
    from praisonai.integrations import ClaudeCodeIntegration, ManagedAgent

    # CLI tool integration
    claude = ClaudeCodeIntegration(workspace="/path/to/project")

    # Managed agent integration
    managed = ManagedAgent(config={"model": "claude-sonnet-4-6"})

    # Use as agent tool
    tool = claude.as_tool()

    # Or execute directly
    result = await claude.execute("Refactor this code")

Public surface
    Backed by a static name -> lazy-loader map plus the entry-point group
    ``praisonai.integrations`` for third-party plugins. There is no third
    registry: CLI backends and managed backends keep their own typed registries
    (:class:`ExternalAgentRegistry`, :class:`ManagedBackendRegistry`) as the
    sources of truth for the ``--external-agent`` and ``run_on=`` surfaces.

Third-party plugins::

        # your-plugin/pyproject.toml
        [project.entry-points."praisonai.integrations"]
        acme = "acme_praison:AcmeIntegration"

        # after `pip install your-plugin`
        from praisonai.integrations import acme

    Names that collide with a built-in integration are ignored — built-ins
    always win.
"""

from typing import Any, Callable, Dict

# Lazy imports to avoid performance impact
__all__ = [
    'BaseCLIIntegration',
    'CLIExecutionError',
    'ClaudeCodeIntegration',
    'GeminiCLIIntegration',
    'CodexCLIIntegration',
    'CursorCLIIntegration',
    'ManagedAgent',
    'ManagedConfig',
    'AnthropicManagedAgent',
    'LocalManagedAgent',           # backward compat alias
    'LocalManagedConfig',          # backward compat alias
    'SandboxedAgent',              # new honest name
    'SandboxedAgentConfig',        # new honest name
    'ManagedAgentIntegration',     # backward compat alias
    'ManagedBackendConfig',        # backward compat alias
    # New canonical agent backends
    'HostedAgent',
    'HostedAgentConfig',
    'LocalAgent',
    'LocalAgentConfig',
    'get_available_integrations',
    'ExternalAgentRegistry',
    'get_registry',
    'register_integration',
    'create_integration',
]


def _load(dotted: str) -> Any:
    """Import ``module:attr`` lazily and return the attribute."""
    from importlib import import_module

    module_name, _, attr = dotted.partition(":")
    return getattr(import_module(module_name), attr)


# name -> "module:attr". Each symbol is owned by its real module; this map keeps
# the __init__ import graph flat and avoids a third registry that re-declares
# what the owning modules already export.
_STATIC_EXPORTS: Dict[str, str] = {
    "BaseCLIIntegration": "praisonai.integrations.base:BaseCLIIntegration",
    "CLIExecutionError": "praisonai.integrations.base:CLIExecutionError",
    "get_available_integrations": "praisonai.integrations.base:get_available_integrations",
    "ClaudeCodeIntegration": "praisonai.integrations.claude_code:ClaudeCodeIntegration",
    "GeminiCLIIntegration": "praisonai.integrations.gemini_cli:GeminiCLIIntegration",
    "CodexCLIIntegration": "praisonai.integrations.codex_cli:CodexCLIIntegration",
    "CursorCLIIntegration": "praisonai.integrations.cursor_cli:CursorCLIIntegration",
    "ManagedAgent": "praisonai.integrations.managed_agents:ManagedAgent",
    "AnthropicManagedAgent": "praisonai.integrations.managed_agents:AnthropicManagedAgent",
    "ManagedConfig": "praisonai.integrations.managed_agents:ManagedConfig",
    "ManagedBackendConfig": "praisonai.integrations.managed_agents:ManagedConfig",
    "LocalManagedAgent": "praisonai.integrations.managed_local:LocalManagedAgent",
    "LocalManagedConfig": "praisonai.integrations.managed_local:LocalManagedConfig",
    "SandboxedAgent": "praisonai.integrations.managed_local:SandboxedAgent",
    "SandboxedAgentConfig": "praisonai.integrations.managed_local:SandboxedAgentConfig",
    "HostedAgent": "praisonai.integrations.hosted_agent:HostedAgent",
    "HostedAgentConfig": "praisonai.integrations.hosted_agent:HostedAgentConfig",
    "LocalAgent": "praisonai.integrations.local_agent:LocalAgent",
    "LocalAgentConfig": "praisonai.integrations.local_agent:LocalAgentConfig",
    "ExternalAgentRegistry": "praisonai.integrations.registry:ExternalAgentRegistry",
    "get_registry": "praisonai.integrations.registry:get_registry",
    "register_integration": "praisonai.integrations.registry:register_integration",
    "create_integration": "praisonai.integrations.registry:create_integration",
}

# Backward-compat aliases handled by ManagedAgent's own module already, but the
# public surface historically exposed these two names too.
_ALIASES: Dict[str, str] = {
    "ManagedAgentIntegration": "ManagedAgent",
}


def _entry_point_plugin(name: str) -> Any:
    """Resolve a third-party ``praisonai.integrations`` plugin by name.

    Built-ins always win (they are served by ``_STATIC_EXPORTS`` before this is
    consulted), so a plugin may only *add* names, never replace a shipped one.
    """
    try:
        from importlib.metadata import entry_points
    except Exception:  # pragma: no cover
        return None
    try:
        eps = entry_points(group="praisonai.integrations")
    except TypeError:
        eps = entry_points().get("praisonai.integrations", [])
    except Exception:
        return None
    for ep in eps:
        if ep.name == name:
            try:
                return ep.load()
            except Exception:
                return None
    return None


def __getattr__(name: str) -> Any:
    """Lazy load integrations from the static map, then entry-point plugins.

    Submodule names (dunder / private modules) must fall through to normal
    import machinery so ``from praisonai.integrations import <submodule>``
    keeps working.
    """
    if name.startswith("_"):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    canonical = _ALIASES.get(name, name)
    dotted = _STATIC_EXPORTS.get(canonical)
    if dotted is not None:
        return _load(dotted)

    plugin = _entry_point_plugin(name)
    if plugin is not None:
        return plugin

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
