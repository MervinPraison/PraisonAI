"""Subprocess execution that cannot hang the caller indefinitely.

Several gateway paths shell out while an asyncio event loop is waiting on
them. ``subprocess.run`` without ``timeout=`` blocks forever if the child
waits on stdin -- a git credential prompt, an ``index.lock`` contention, a
confirmation prompt -- and the whole gateway stops serving.

``subprocess.run(timeout=...)`` alone is not enough, because it only kills
the *direct* child:

* On POSIX its timeout path calls ``kill()`` then ``wait()``. The call
  returns, but any grandchild the command spawned is orphaned and keeps
  running.
* On Windows it calls ``kill()`` then ``communicate()`` with **no timeout**.
  A surviving grandchild that inherited the captured stdout/stderr pipe holds
  it open, so that ``communicate()`` blocks until the grandchild exits --
  reintroducing exactly the indefinite hang this module exists to prevent.

That is not hypothetical for the calls here: ``git`` routinely spawns
credential helpers and transport processes, and a stuck credential helper is
the motivating failure.

:func:`run_guarded` therefore runs the command in its own process group (or
Windows process group), kills the whole group on timeout, and then reaps
with a *bounded* second wait so a stubborn descendant can never block the
caller.

Note on semantics: this is a total-runtime cap, not an inactivity timer. A
command that streams output steadily for longer than the cap is still killed.
Callers with legitimately long work should pass an explicit ``timeout``.
"""

from __future__ import annotations

import logging
import math
import os
import signal
import subprocess
from typing import Mapping, Optional, Sequence

__all__ = ["run_guarded", "DEFAULT_TIMEOUT", "TIMEOUT_RETURNCODE", "diagnose"]

logger = logging.getLogger(__name__)

#: Total seconds a guarded command may run before it is killed.
#: Override per call, or globally via ``PRAISONAI_SUBPROCESS_TIMEOUT``.
DEFAULT_TIMEOUT = 120.0

#: Returncode reported for a killed command. 124 is the conventional exit
#: status used by coreutils ``timeout``.
TIMEOUT_RETURNCODE = 124

#: Seconds allowed for the post-kill reap. Bounded on purpose: if a
#: descendant somehow survives the group kill and still holds the pipe, we
#: abandon the output rather than block the caller.
REAP_TIMEOUT = 5.0

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
    """Resolve the global timeout, ignoring an unusable env override.

    ``inf`` is rejected alongside zero and negatives: it parses cleanly and is
    positive, so a bare ``value > 0`` check would accept it and hand back an
    unbounded wait -- reinstating the exact hang this module prevents. ``nan``
    fails the comparison on its own, but is covered explicitly for clarity.
    """
    raw = os.environ.get(_ENV_TIMEOUT)
    if not raw:
        return DEFAULT_TIMEOUT
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT
    if not math.isfinite(value) or value <= 0:
        return DEFAULT_TIMEOUT
    return value


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


def _kill_process_group(proc: subprocess.Popen) -> None:
    """Terminate the command *and everything it spawned*.

    Killing only the direct child leaves grandchildren holding the inherited
    stdout/stderr pipe, which is what turns a bounded call back into a hang.
    """
    if os.name == "nt":
        try:
            # /T walks the tree, /F forces. Bounded so the cleanup itself
            # cannot become the new hang.
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=REAP_TIMEOUT,
            )
        except Exception:  # pragma: no cover - Windows-only path
            _kill_direct(proc)
        return

    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        # Already gone, or we could not resolve the group; fall back.
        _kill_direct(proc)


def _kill_direct(proc: subprocess.Popen) -> None:
    """Last-resort kill of the direct child only."""
    try:
        proc.kill()
    except Exception:  # pragma: no cover - process already reaped
        pass


def _reap(proc: subprocess.Popen) -> tuple[str, str]:
    """Collect whatever output is available without blocking indefinitely."""
    try:
        return proc.communicate(timeout=REAP_TIMEOUT)
    except subprocess.TimeoutExpired:
        # A descendant survived the group kill and still holds the pipe.
        # Abandon the output rather than block the caller -- returning late
        # is the failure mode this module exists to prevent.
        logger.warning(
            "Guarded command %s left a descendant holding its output pipe; "
            "abandoning captured output after %.0fs.",
            proc.args,
            REAP_TIMEOUT,
        )
        for stream in (proc.stdout, proc.stderr):
            try:
                if stream is not None:
                    stream.close()
            except Exception:  # pragma: no cover - best effort
                pass
        return "", ""
    except Exception:  # pragma: no cover - defensive
        return "", ""


def run_guarded(
    cmd: Sequence[str],
    *,
    timeout: Optional[float] = None,
    cwd: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    interactive: bool = False,
    check: bool = False,
    text: bool = True,
    capture_output: bool = True,
    **kwargs,
) -> subprocess.CompletedProcess:
    """Run ``cmd`` with a bounded runtime, never raising on timeout.

    Behaves like ``subprocess.run(..., capture_output=True, text=True)``. On
    timeout the whole process group is killed and a
    :class:`subprocess.CompletedProcess` is returned with returncode
    :data:`TIMEOUT_RETURNCODE` and a diagnosis appended to stderr, so existing
    ``returncode == 0`` checks keep working instead of having to grow a new
    exception path.

    Args:
        cmd: Command and arguments.
        timeout: Total seconds allowed. Defaults to
            ``PRAISONAI_SUBPROCESS_TIMEOUT`` or :data:`DEFAULT_TIMEOUT`.
        cwd: Working directory.
        env: Environment; prompt-suppressing defaults are layered underneath.
        interactive: Set True only for a command that must reach a terminal.
            Skips prompt suppression and stdin redirection; the timeout and
            the group kill still apply.
        check: Raise ``CalledProcessError`` on a non-zero exit, matching
            ``subprocess.run``. A timeout still returns rather than raising.
        text: Decode output as text.
        capture_output: Capture stdout and stderr.
        **kwargs: Forwarded to ``subprocess.Popen``.
    """
    resolved_timeout = _default_timeout() if timeout is None else timeout

    if capture_output:
        kwargs.setdefault("stdout", subprocess.PIPE)
        kwargs.setdefault("stderr", subprocess.PIPE)

    # stdin at /dev/null turns "wait forever for input" into an immediate EOF
    # for tools that honour it, so the timeout is a backstop rather than the
    # primary defence.
    if not interactive:
        kwargs.setdefault("stdin", subprocess.DEVNULL)

    # Isolate the command so the whole tree can be killed together.
    if os.name == "nt":
        kwargs["creationflags"] = (
            kwargs.get("creationflags", 0) | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs.setdefault("start_new_session", True)

    argv = list(cmd)
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env if interactive else _non_interactive_env(env),
        text=text,
        **kwargs,
    )

    try:
        stdout, stderr = proc.communicate(timeout=resolved_timeout)
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
        stdout, stderr = _reap(proc)
        stdout = _as_text(stdout)
        stderr = _as_text(stderr)
        # Built outside the f-string: a backslash inside an f-string
        # expression is a syntax error before Python 3.12, and this package
        # supports 3.10+.
        captured = stdout + "\n" + stderr
        detail = (
            f"Command killed after {resolved_timeout:g}s: {' '.join(argv)}\n"
            f"{diagnose(captured)}"
        )
        return subprocess.CompletedProcess(
            args=argv,
            returncode=TIMEOUT_RETURNCODE,
            stdout=stdout,
            stderr=(stderr + "\n" + detail).strip(),
        )
    except BaseException:
        # Never leave a running child behind on an unexpected error, including
        # KeyboardInterrupt.
        _kill_process_group(proc)
        _reap(proc)
        raise

    result = subprocess.CompletedProcess(
        args=argv,
        returncode=proc.returncode,
        stdout=_as_text(stdout) if capture_output else stdout,
        stderr=_as_text(stderr) if capture_output else stderr,
    )
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, argv, result.stdout, result.stderr
        )
    return result


def _as_text(value) -> str:
    """Normalise stdout/stderr, which may be bytes, None, or already str."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)
