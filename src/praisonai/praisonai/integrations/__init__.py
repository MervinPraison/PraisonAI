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


def __getattr__(name: str):
    """Lazy load integrations using unified registry."""
    from ._unified_registry import INTEGRATIONS_REGISTRY
    return INTEGRATIONS_REGISTRY.get_by_attr(__name__, name)
