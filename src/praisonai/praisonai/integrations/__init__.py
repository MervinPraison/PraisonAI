"""
PraisonAI Integrations - External CLI tool integrations.

This module provides integrations with external AI coding CLI tools:
- Claude Code CLI
- Gemini CLI
- OpenAI Codex CLI
- Cursor CLI

All integrations use lazy loading to avoid performance impact.

Usage:
    from praisonai.integrations import ClaudeCodeIntegration, GeminiCLIIntegration
    
    # Create integration
    claude = ClaudeCodeIntegration(workspace="/path/to/project")
    
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
    'get_available_integrations',
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
    elif name == 'get_available_integrations':
        from .base import get_available_integrations
        return get_available_integrations
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
