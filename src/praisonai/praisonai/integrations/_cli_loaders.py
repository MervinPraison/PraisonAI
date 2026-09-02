"""Canonical lazy loaders for the built-in CLI-backend integrations.

Defined once here and consumed by :class:`ExternalAgentRegistry` (the single
source of truth for the ``--external-agent`` surface) so a new backend only
ever has to be registered in a single place.
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


BUILTIN_INTEGRATIONS: Dict[str, Callable[[], Any]] = {
    "claude": load_claude_code,
    "gemini": load_gemini_cli,
    "codex": load_codex_cli,
    "cursor": load_cursor_cli,
}
