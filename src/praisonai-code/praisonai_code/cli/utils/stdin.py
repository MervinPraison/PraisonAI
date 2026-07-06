"""
Shared stdin ingestion helpers for the PraisonAI CLI.

Provides a single, EOF-safe implementation of "read piped stdin" so the modern
Typer commands (``run``/``code``/``chat``) and the legacy bare-prompt path all
behave identically as Unix filters:

    cat error.log | praisonai run  "Diagnose the root cause"
    git diff       | praisonai run  "Review these changes"

Reading is guarded by ``select.select`` (Unix) or a stat-based pipe check plus a
bounded read (Windows) so an interactive TTY (or a pipe with no EOF, common in
CI/CD, subprocesses, IDE terminals, and Docker) is never stalled.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

logger = logging.getLogger(__name__)

# Safety cap so an accidentally huge pipe (e.g. `cat huge.bin | praisonai run`)
# can't buffer unbounded memory before the agent even starts.
_MAX_STDIN_BYTES = 10 * 1024 * 1024  # 10 MB


def _windows_stdin_is_pipe() -> bool:
    """Return ``True`` when Windows stdin is a pipe/file (not a console/TTY).

    ``select.select`` is socket-only on Windows, so we cannot use it to detect
    ready pipe data. Instead we classify the stdin handle: a redirected pipe or
    file (``type f | praisonai`` / ``praisonai < f``) has data to read, whereas a
    console is caught earlier by ``isatty()``. This never blocks because a
    redirected handle reports EOF at the end of its content.
    """
    try:
        import stat

        mode = os.fstat(sys.stdin.fileno()).st_mode
        # Named pipe (FIFO) or a regular file redirection both carry piped data.
        return stat.S_ISFIFO(mode) or stat.S_ISREG(mode)
    except Exception:
        return False


def _stdin_has_data() -> bool:
    """Non-blocking check for whether piped stdin data is available to read.

    Uses ``select.select`` on Unix (supports pipes) and a stat-based pipe/file
    classification on Windows (where ``select`` is socket-only). Either way the
    caller never blocks on an interactive TTY or an EOF-less pipe.
    """
    if sys.platform.startswith("win"):
        return _windows_stdin_is_pipe()

    import select

    # Non-blocking check: only read if data is actually available. Without this,
    # sys.stdin.read() blocks forever in non-TTY environments (subprocesses,
    # CI/CD, IDE terminals, Docker) where stdin is a pipe with no EOF.
    return bool(select.select([sys.stdin], [], [], 0.0)[0])


def read_stdin_if_available() -> Optional[str]:
    """Read piped stdin content if available.

    Returns the stripped stdin content, or ``None`` when stdin is a TTY, has no
    data available, or reading fails. Non-blocking: uses ``select.select`` on
    Unix and a stat-based pipe check on Windows so an open pipe with no EOF (or
    an interactive console) never blocks the caller.

    Reads at most ``_MAX_STDIN_BYTES`` to bound memory.
    """
    try:
        # A TTY means interactive input, not piped data.
        if sys.stdin.isatty():
            return None

        if _stdin_has_data():
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
