"""
Shared stdin ingestion helpers for the PraisonAI CLI.

Provides a single, EOF-safe implementation of "read piped stdin" so the modern
Typer commands (``run``/``code``/``chat``) and the legacy bare-prompt path all
behave identically as Unix filters:

    cat error.log | praisonai run  "Diagnose the root cause"
    git diff       | praisonai run  "Review these changes"

Reading is guarded by ``select.select`` so an interactive TTY (or a pipe with no
EOF, common in CI/CD, subprocesses, IDE terminals, and Docker) is never stalled.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

logger = logging.getLogger(__name__)

# Safety cap so an accidentally huge pipe (e.g. `cat huge.bin | praisonai run`)
# can't buffer unbounded memory before the agent even starts.
_MAX_STDIN_BYTES = 10 * 1024 * 1024  # 10 MB


def read_stdin_if_available() -> Optional[str]:
    """Read piped stdin content if available.

    Returns the stripped stdin content, or ``None`` when stdin is a TTY, has no
    data available, or reading fails. Non-blocking: uses ``select.select`` so an
    open pipe with no EOF never blocks the caller.

    Reads at most ``_MAX_STDIN_BYTES`` to bound memory. On platforms where
    ``select.select`` does not support pipes (notably Windows), the read is
    skipped rather than risking a block.
    """
    try:
        # A TTY means interactive input, not piped data.
        if sys.stdin.isatty():
            return None

        # select.select() only supports pipes/stdin on Unix-like platforms; on
        # Windows it is socket-only, so skip the piped-read path there rather
        # than blocking on sys.stdin.read().
        if sys.platform.startswith("win"):
            return None

        import select

        # Non-blocking check: only read if data is actually available. Without
        # this, sys.stdin.read() blocks forever in non-TTY environments
        # (subprocesses, CI/CD, IDE terminals, Docker) where stdin is a pipe
        # with no EOF.
        if select.select([sys.stdin], [], [], 0.0)[0]:
            stdin_content = sys.stdin.read(_MAX_STDIN_BYTES).strip()
            return stdin_content if stdin_content else None
    except Exception:
        # If there's any error reading stdin, don't crash the CLI — fall through
        # to None, but log at debug level so piping issues remain diagnosable.
        logger.debug("Failed to read piped stdin", exc_info=True)
    return None


def resolve_cli_input(prompt: Optional[str], *, allow_stdin: bool = True) -> Optional[str]:
    """Merge a prompt argument with any piped stdin content.

    The prompt argument comes first, then the piped body (matching the legacy
    behaviour). If only piped input is present, it becomes the input. Interactive
    (TTY) invocations are untouched, so ``isatty()``-based mode detection in the
    callers is preserved.

    Args:
        prompt: The prompt argument supplied on the command line, if any.
        allow_stdin: When ``False``, stdin is never read and ``prompt`` is
            returned unchanged (e.g. for interactive REPL entry points).

    Returns:
        The combined prompt string, or ``None`` when neither a prompt nor piped
        input is present.
    """
    if not allow_stdin:
        return prompt

    piped = read_stdin_if_available()
    parts = [part for part in (prompt, piped) if part]
    if not parts:
        return prompt
    return "\n".join(parts)
