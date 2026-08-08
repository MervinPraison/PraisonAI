"""Resolve the ``--append-system-prompt`` CLI value.

Shared by the ``code``, ``chat`` and ``run`` commands. Accepts either literal
text or an ``@file`` reference (the file's contents are read), and falls back to
the ``PRAISONAI_APPEND_SYSTEM_PROMPT`` environment variable for CI.

Uses only the standard library to keep import cost at zero.
"""

import os
from typing import Optional

ENV_VAR = "PRAISONAI_APPEND_SYSTEM_PROMPT"


def resolve_append_system_prompt(value: Optional[str]) -> Optional[str]:
    """Resolve the append-system-prompt value from a flag or the environment.

    Args:
        value: The raw ``--append-system-prompt`` value. May be ``None``,
            literal text, or an ``@file`` reference such as ``@prompt.txt``.

    Returns:
        The resolved text to append, or ``None`` when nothing was provided.
        An ``@file`` reference reads the file's contents; a missing file falls
        back to the literal value so behaviour is never surprising.
    """
    if value is None:
        env_value = os.environ.get(ENV_VAR)
        return env_value if env_value and env_value.strip() else None

    text = value.strip()
    if not text:
        return None

    if text.startswith("@"):
        path = os.path.expanduser(text[1:])
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return handle.read().strip() or None
        except OSError:
            # File unreadable: treat the raw value as literal text rather than
            # failing the whole invocation.
            return text

    return text


def apply_append_system_prompt(value: Optional[str]) -> Optional[str]:
    """Resolve the value and export it via :data:`ENV_VAR` for agent construction.

    The environment variable is the single choke point read by the core Agent
    when assembling its system prompt, so every construction path (interactive
    TUI, single-prompt, YAML, Python) picks it up without threading a new
    parameter through each call site.

    Returns the resolved text (or ``None`` when nothing was provided).
    """
    resolved = resolve_append_system_prompt(value)
    if resolved:
        os.environ[ENV_VAR] = resolved
    return resolved
