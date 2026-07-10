"""Canonical lazy loaders for the built-in CLI-backend integrations.

Defined once here and shared by every registry surface (the unified
``IntegrationRegistry`` and the ``ExternalAgentRegistry``) so a new backend
only ever has to be registered in a single place. Previously these four
loaders were hand-duplicated across ``_unified_registry.py`` and
``registry.py``; a single-sided edit silently disappeared from one lookup
surface.
"""

from typing import Any, Callable, Dict


def load_claude_code() -> Any:
    from .claude_code import ClaudeCodeIntegration
    return ClaudeCodeIntegration


def load_gemini_cli() -> Any:
    from .gemini_cli import GeminiCLIIntegration
    return GeminiCLIIntegration


def load_codex_cli() -> Any:
    from .codex_cli import CodexCLIIntegration
    return CodexCLIIntegration


def load_cursor_cli() -> Any:
    from .cursor_cli import CursorCLIIntegration
    return CursorCLIIntegration


CLASS_NAME_LOADERS: Dict[str, Callable[[], Any]] = {
    "ClaudeCodeIntegration": load_claude_code,
    "GeminiCLIIntegration": load_gemini_cli,
    "CodexCLIIntegration": load_codex_cli,
    "CursorCLIIntegration": load_cursor_cli,
}

BUILTIN_INTEGRATIONS: Dict[str, Callable[[], Any]] = {
    "claude": load_claude_code,
    "gemini": load_gemini_cli,
    "codex": load_codex_cli,
    "cursor": load_cursor_cli,
}
