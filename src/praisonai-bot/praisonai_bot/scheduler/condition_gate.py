"""
Pre-run condition gates for the scheduler (bot layer).

A *condition gate* is a cheap, deterministic check that decides whether a
scheduled job's (expensive) model turn should happen at all. It implements the
core ``JobConditionProtocol`` and returns a ``GateResult``:

- ``run=False`` → the tick is recorded as ``skipped``; no model tokens are
  spent and no empty message is delivered.
- ``run=True`` → the run proceeds. Any text the gate produces is exposed as
  ``context`` and appended to the job message, so the same check both *gates*
  the run and *seeds* it with context.

This is a **cost/efficiency** concern, complementary to (and distinct from) the
wrapper's ``RunPolicy``, which is a **safety** gate on *what* a run may do.

The default :class:`ShellConditionGate` runs the job's ``pre_run`` value as a
shell command:

- exit code ``0`` with output → run, output becomes context;
- exit code ``0`` with empty output → run, no context;
- non-zero exit code → skip (nothing to do).

Deployments wanting a richer gate (a Python callable, an MCP/tool probe) can
supply any object implementing ``JobConditionProtocol`` — the executor accepts a
``condition_resolver`` for exactly this.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
from typing import Any

from praisonaiagents.scheduler.protocols import GateResult

logger = logging.getLogger(__name__)

# On POSIX, start the shell in its own session so a timeout can kill the whole
# process group (shell + any children it spawned) rather than orphaning them.
_POSIX = os.name == "posix"

# Cap captured gate output so a chatty pre-run script cannot blow up the prompt.
_MAX_CONTEXT_CHARS = 8000
# Cap stderr surfaced in the skip ``reason`` so an audit record stays compact.
_MAX_REASON_CHARS = 500


class ShellConditionGate:
    """Default pre-run gate: evaluate ``job.pre_run`` as a shell command.

    Implements the core ``JobConditionProtocol``.

    Args:
        timeout: Maximum seconds the pre-run command may run before it is
            treated as a failure (skip). Defaults to 30s.
    """

    def __init__(self, *, timeout: float = 30.0) -> None:
        self._timeout = timeout

    def should_run(self, job: Any) -> GateResult:
        command = (getattr(job, "pre_run", None) or "").strip()
        if not command:
            # No gate configured → always run (unconditional, as today).
            return GateResult(run=True)

        # On POSIX, run the shell in a new session (its own process group) so a
        # timeout kills the whole group — otherwise ``subprocess.run`` only kills
        # the shell and leaves any children it spawned running as orphans.
        popen_kwargs: dict = {}
        if _POSIX:
            popen_kwargs["start_new_session"] = True

        proc = None
        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                **popen_kwargs,
            )
            stdout, stderr = proc.communicate(timeout=self._timeout)
            completed = subprocess.CompletedProcess(
                command, proc.returncode, stdout, stderr,
            )
        except subprocess.TimeoutExpired:
            # Kill the whole process group (POSIX) so children don't orphan,
            # then reap the shell to avoid a zombie.
            if proc is not None:
                try:
                    if _POSIX:
                        os.killpg(os.getpgid(proc.pid), 9)
                    else:  # pragma: no cover - non-POSIX
                        proc.kill()
                except (ProcessLookupError, PermissionError, OSError):  # pragma: no cover
                    proc.kill()
                try:
                    proc.communicate(timeout=5)
                except Exception:  # pragma: no cover - best-effort reap
                    pass
            logger.warning(
                "Pre-run gate timed out for job '%s' (>%.0fs); skipping tick",
                getattr(job, "id", "?"), self._timeout,
            )
            return GateResult(
                run=False,
                reason=f"pre-run gate timed out (>{self._timeout:.0f}s)",
            )
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(
                "Pre-run gate failed to launch for job '%s': %s; skipping tick",
                getattr(job, "id", "?"), e,
            )
            return GateResult(run=False, reason=f"pre-run gate error: {e}")

        if completed.returncode != 0:
            # Surface a truncated stderr so audit/logs can distinguish a genuine
            # "nothing to do" from a misconfigured gate (auth failure, missing
            # binary, etc.) rather than discarding the diagnostic entirely.
            stderr = (completed.stderr or "").strip()
            reason = "pre-run gate: nothing to do"
            if stderr:
                if len(stderr) > _MAX_REASON_CHARS:
                    stderr = stderr[:_MAX_REASON_CHARS] + "…"
                reason = f"{reason} (exit {completed.returncode}: {stderr})"
            return GateResult(run=False, reason=reason)

        output = (completed.stdout or "").strip()
        if len(output) > _MAX_CONTEXT_CHARS:
            output = output[:_MAX_CONTEXT_CHARS]
        context = output or None
        return GateResult(run=True, context=context)

    # Allow the gate to be referenced by command string directly (helper).
    @staticmethod
    def quote(command: str) -> str:
        """Return a shell-safe quoting of ``command`` (convenience helper)."""
        return shlex.quote(command)
