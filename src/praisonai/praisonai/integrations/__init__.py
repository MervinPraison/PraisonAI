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
"""

# Lazy imports to avoid performance impact
__all__ = [
    'BaseCLIIntegration',
    'ClaudeCodeIntegration',
    'GeminiCLIIntegration',
    'CodexCLIIntegration',
    'CursorCLIIntegration',
    'ManagedAgent',
    'ManagedConfig',
    'AnthropicManagedAgent',
    'LocalManagedAgent',
    'LocalManagedConfig',
    'ManagedAgentIntegration',  # backward compat alias
    'ManagedBackendConfig',     # backward compat alias
    'get_available_integrations',
    'ExternalAgentRegistry',
    'get_registry',
    'register_integration',
    'create_integration',
]


def __getattr__(name):
    """Lazy load integrations to minimize import overhead."""
    if name == 'BaseCLIIntegration':
        from .base import BaseCLIIntegration
        return BaseCLIIntegration
    elif name == 'ClaudeCodeIntegration':
        from .claude_code import ClaudeCodeIntegration
        return ClaudeCodeIntegration
    elif name == 'GeminiCLIIntegration':
        from .gemini_cli import GeminiCLIIntegration
        return GeminiCLIIntegration
    elif name == 'CodexCLIIntegration':
        from .codex_cli import CodexCLIIntegration
        return CodexCLIIntegration
    elif name == 'CursorCLIIntegration':
        from .cursor_cli import CursorCLIIntegration
        return CursorCLIIntegration
    elif name in ('ManagedAgent', 'ManagedAgentIntegration'):
        from .managed_agents import ManagedAgent
        return ManagedAgent
    elif name == 'AnthropicManagedAgent':
        from .managed_agents import AnthropicManagedAgent
        return AnthropicManagedAgent
    elif name == 'LocalManagedAgent':
        from .managed_local import LocalManagedAgent
        return LocalManagedAgent
    elif name == 'LocalManagedConfig':
        from .managed_local import LocalManagedConfig
        return LocalManagedConfig
    elif name in ('ManagedConfig', 'ManagedBackendConfig'):
        from .managed_agents import ManagedConfig
        return ManagedConfig
    elif name == 'get_available_integrations':
        from .registry import get_available_integrations
        return get_available_integrations
    elif name == 'ExternalAgentRegistry':
        from .registry import ExternalAgentRegistry
        return ExternalAgentRegistry
    elif name == 'get_registry':
        from .registry import get_registry
        return get_registry
    elif name == 'register_integration':
        from .registry import register_integration
        return register_integration
    elif name == 'create_integration':
        from .registry import create_integration
        return create_integration
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
