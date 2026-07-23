"""CLI backend helpers for hooks and observability."""

from __future__ import annotations

from typing import Any


def backend_label(backend: Any) -> str:
    """Human-readable backend identifier for hooks and logs."""
    config = getattr(backend, "config", None)
    command = getattr(config, "command", None)
    if command:
        return str(command)
    return type(backend).__name__


_PROMPT_FLAGS = frozenset(
    {"-p", "--prompt", "-i", "--input", "-m", "--message", "--system"}
)


def redact_command(command: Any) -> Any:
    """Redact prompt/system values from a subprocess argv for safe serialization.

    Keeps the executable and flags visible for verification while masking the
    value that follows a known prompt-bearing flag, since that value may carry
    user prompts or system instructions that should not leak into log sinks.
    Non-list inputs are returned unchanged.
    """
    if not isinstance(command, (list, tuple)):
        return command
    redacted = []
    mask_next = False
    for arg in command:
        if mask_next:
            redacted.append("<redacted>")
            mask_next = False
            continue
        redacted.append(arg)
        if isinstance(arg, str) and arg in _PROMPT_FLAGS:
            mask_next = True
    return redacted
