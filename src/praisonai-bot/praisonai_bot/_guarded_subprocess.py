"""Subprocess execution that cannot hang the caller indefinitely.

Several gateway paths shell out while an asyncio event loop is waiting on
them. ``subprocess.run`` without ``timeout=`` blocks forever if the child
waits on stdin -- a git credential prompt, an ``index.lock`` contention, a
confirmation prompt -- and the whole gateway stops serving.

This module provides :func:`run_guarded`, a drop-in replacement that always
bounds the call and, when it does fire, hands the caller a *diagnosis* rather
than a bare timeout. Knowing that a command died waiting on a confirmation
prompt is actionable; knowing only that 120 seconds elapsed is not.

Note on semantics: this is a total-runtime cap, not an inactivity timer. A
command that streams output steadily for longer than the cap is still killed.
Callers with legitimately long work should pass an explicit ``timeout``.
"""

from __future__ import annotations

import os
import subprocess
from typing import Mapping, Optional, Sequence

__all__ = ["run_guarded", "DEFAULT_TIMEOUT", "diagnose"]

#: Total seconds a guarded command may run before it is killed.
#: Override per call, or globally via ``PRAISONAI_SUBPROCESS_TIMEOUT``.
DEFAULT_TIMEOUT = 120.0

#: Returncode reported for a killed command. 124 is the conventional exit
#: status used by coreutils ``timeout``.
TIMEOUT_RETURNCODE = 124

_ENV_TIMEOUT = "PRAISONAI_SUBPROCESS_TIMEOUT"

# Substrings that identify why a child process is sitting idle. Ordered most
# specific first; the first hit wins.
_SIGNATURES: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("username for", "password for", "passphrase", "authentication failed"),
        "DETECTED: credential prompt. The command is waiting for a login that "
        "will never arrive. Configure a credential helper, or set "
        "GIT_TERMINAL_PROMPT=0 so it fails fast instead of blocking.",
    ),
    (
        ("index.lock", "unable to create", "another git process"),
        "DETECTED: git lock contention. Another git process holds the "
        "repository lock. Retry once it exits, or remove a stale .git/index.lock.",
    ),
    (
        ("[y/n]", "(yes/no)", "are you sure", "continue?", "overwrite?", "proceed?"),
        "DETECTED: confirmation prompt. Re-run non-interactively with the "
        "command's own flag (--yes, -y, --force, --no-confirm).",
    ),
    (
        ("host key", "fingerprint", "known_hosts"),
        "DETECTED: SSH host-key prompt. Pre-populate known_hosts, or pass "
        "-o StrictHostKeyChecking=accept-new.",
    ),
)

_GENERIC = (
    "No interactive prompt was detected. The command may be genuinely slow, "
    "blocked on network I/O, or deadlocked. Raise timeout= if the work is "
    "expected to take longer."
)


def diagnose(captured: str) -> str:
    """Return a human- and model-actionable reason a command stalled.

    ``captured`` is whatever the child emitted before it was killed; it may be
    empty, which is itself common for a process blocked on stdin.
    """
    haystack = (captured or "").lower()
    for needles, message in _SIGNATURES:
        if any(needle in haystack for needle in needles):
            return message
    return _GENERIC


def _default_timeout() -> float:
    """Resolve the global timeout, ignoring an unusable env override."""
    raw = os.environ.get(_ENV_TIMEOUT)
    if not raw:
        return DEFAULT_TIMEOUT
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT
    return value if value > 0 else DEFAULT_TIMEOUT


def _non_interactive_env(env: Optional[Mapping[str, str]]) -> dict:
    """Environment that makes common tools fail rather than prompt.

    Suppressing the prompt at source is better than killing the process after
    it hangs: the command returns an error the caller can act on immediately.
    """
    resolved = dict(env if env is not None else os.environ)
    resolved.setdefault("GIT_TERMINAL_PROMPT", "0")
    resolved.setdefault("GCM_INTERACTIVE", "never")
    resolved.setdefault("DEBIAN_FRONTEND", "noninteractive")
    return resolved


def run_guarded(
    cmd: Sequence[str],
    *,
    timeout: Optional[float] = None,
    cwd: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    interactive: bool = False,
    **kwargs,
) -> subprocess.CompletedProcess:
    """Run ``cmd`` with a bounded runtime, never raising on timeout.

    Behaves like ``subprocess.run(..., capture_output=True, text=True)``. On
    timeout the child is killed and a :class:`subprocess.CompletedProcess` is
    returned with returncode :data:`TIMEOUT_RETURNCODE` and a diagnosis
    appended to stderr, so existing ``returncode == 0`` checks keep working
    instead of having to grow a new exception path.

    Args:
        cmd: Command and arguments.
        timeout: Total seconds allowed. Defaults to
            ``PRAISONAI_SUBPROCESS_TIMEOUT`` or :data:`DEFAULT_TIMEOUT`.
        cwd: Working directory.
        env: Environment; prompt-suppressing defaults are layered underneath.
        interactive: Set True only for a command that must reach a terminal.
            Skips prompt suppression; the timeout still applies.
        **kwargs: Forwarded to ``subprocess.run``.
    """
    resolved_timeout = _default_timeout() if timeout is None else timeout
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)

    # stdin at /dev/null turns "wait forever for input" into an immediate EOF
    # for tools that honour it, so the timeout is a backstop rather than the
    # primary defence.
    if not interactive:
        kwargs.setdefault("stdin", subprocess.DEVNULL)

    try:
        return subprocess.run(
            list(cmd),
            timeout=resolved_timeout,
            cwd=cwd,
            env=env if interactive else _non_interactive_env(env),
            **kwargs,
        )
    except subprocess.TimeoutExpired as exc:
        partial_out = _as_text(exc.stdout)
        partial_err = _as_text(exc.stderr)
        reason = diagnose(f"{partial_out}\n{partial_err}")
        detail = (
            f"Command killed after {resolved_timeout:g}s: {' '.join(cmd)}\n"
            f"{reason}"
        )
        return subprocess.CompletedProcess(
            args=list(cmd),
            returncode=TIMEOUT_RETURNCODE,
            stdout=partial_out,
            stderr=(partial_err + "\n" + detail).strip(),
        )


def _as_text(value) -> str:
    """Normalise TimeoutExpired's stdout/stderr, which may be bytes or None."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)
