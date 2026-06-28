"""Crash / shutdown forensics for the gateway (Issue #2436).

The core SDK keeps only the pure contract and decision/formatting helpers
(:class:`praisonaiagents.gateway.ShutdownForensicsProtocol`,
:func:`format_forensics_for_log`, :func:`is_supervised`,
:func:`drain_timeout_has_headroom`). This wrapper module owns the OS-specific,
heavyweight I/O those helpers deliberately avoid: reading ``/proc``, calling
``os.getrusage``/``os.getloadavg``, and spawning a *detached* diagnostic that
survives a ``SIGKILL`` on the process group.

Everything here is best-effort and defensive: a snapshot must never raise and
never block the asyncio teardown, and spawning the diagnostic must never raise.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, Optional

from praisonaiagents.gateway import is_supervised

logger = logging.getLogger(__name__)


def _read_tracer_pid() -> Optional[int]:
    """Return the TracerPid from ``/proc/self/status`` (0 = none), or None."""
    try:
        with open("/proc/self/status", "r") as fh:
            for line in fh:
                if line.startswith("TracerPid:"):
                    return int(line.split(":", 1)[1].strip())
    except (OSError, ValueError):
        return None
    return None


class ShutdownForensics:
    """Concrete forensics capture wired into the gateway signal handlers.

    Conforms to :class:`praisonaiagents.gateway.ShutdownForensicsProtocol`.

    Args:
        log_dir: Directory where the detached diagnostic writes its report.
        enabled: When ``False``, :meth:`spawn_diagnostic` is a no-op (the cheap
            :meth:`snapshot` is still available for logging).
    """

    def __init__(self, log_dir: Optional[str] = None, enabled: bool = True):
        self.log_dir = log_dir
        self.enabled = bool(enabled)
        # Pre-create the diagnostic directory at startup so the signal path
        # never performs synchronous filesystem I/O (a slow/hung FS such as NFS
        # or an automount could otherwise block shutdown before drain). Only a
        # directory we successfully prepared here is used by spawn_diagnostic.
        self._prepared_dir: Optional[str] = None
        if self.enabled and self.log_dir:
            try:
                os.makedirs(self.log_dir, exist_ok=True)
                self._prepared_dir = self.log_dir
            except (OSError, TypeError, ValueError) as exc:
                logger.debug(
                    "forensics: could not prepare diagnostic dir: %s", exc
                )

    def snapshot(self, signal_name: Optional[str] = None) -> Dict[str, Any]:
        """Capture a fast (<10ms), best-effort forensic context.

        Never raises: any failure to read a particular signal simply omits that
        key from the returned dict so the caller can still log what it has.
        """
        ctx: Dict[str, Any] = {}
        if signal_name:
            ctx["signal"] = signal_name
        try:
            ctx["pid"] = os.getpid()
        except Exception:
            pass

        ppid: Optional[int] = None
        try:
            ppid = os.getppid()
            ctx["ppid"] = ppid
        except Exception:
            ppid = None

        invocation_id = os.environ.get("INVOCATION_ID") or None
        try:
            ctx["supervised"] = is_supervised(ppid, invocation_id)
        except Exception:
            pass

        try:
            ctx["loadavg_1m"] = round(os.getloadavg()[0], 2)
        except (OSError, AttributeError):
            pass

        tracer = _read_tracer_pid()
        if tracer is not None:
            ctx["traced"] = tracer > 0

        try:
            import resource

            ctx["maxrss_kb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        except Exception:
            pass

        return ctx

    def spawn_diagnostic(self, ctx: Dict[str, Any], log_dir: Optional[str]) -> None:
        """Fire-and-forget a detached diagnostic that survives ``SIGKILL``.

        Writes recent kernel OOM/killed lines, the process tree, and load into
        ``<log_dir>/gateway-forensics-<pid>.log`` from a process detached via a
        new session (``start_new_session=True``) so a kill on the gateway's
        process group does not also kill the diagnostic. Never raises and never
        performs synchronous filesystem I/O on the signal path: the directory is
        prepared once in ``__init__``.
        """
        if not self.enabled:
            return
        # Only use a directory we already created at startup; this keeps the
        # signal path free of blocking ``os.makedirs`` on a slow/hung FS. A
        # ``log_dir`` argument is honoured only when it is the prepared one.
        target_dir = self._prepared_dir
        if log_dir and log_dir != target_dir:
            return
        if not target_dir:
            return
        try:
            pid = ctx.get("pid", os.getpid())
            out_path = os.path.join(target_dir, f"gateway-forensics-{pid}.log")
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("forensics: could not prepare diagnostic path: %s", exc)
            return

        # A tiny self-contained shell pipeline: it must not depend on the dying
        # parent. Each probe is guarded so a missing tool never aborts the rest.
        script = (
            "{ echo \"# gateway forensics ctx: %(ctx)s\"; "
            "echo '## process tree'; ps -o pid,ppid,stat,rss,etime,cmd "
            "--ppid 1 2>/dev/null || ps aux 2>/dev/null | head -n 40; "
            "echo '## load'; cat /proc/loadavg 2>/dev/null; "
            "echo '## recent kernel OOM/killed'; "
            "(dmesg 2>/dev/null | grep -iE "
            "'killed process|out of memory|oom' | tail -n 20) || true; "
            "} >> %(out)s 2>&1"
        ) % {"ctx": _shell_safe(str(ctx)), "out": _shell_safe(out_path)}

        try:
            import subprocess

            subprocess.Popen(  # noqa: S603 - fixed, non-user shell pipeline
                ["/bin/sh", "-c", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("forensics: could not spawn diagnostic: %s", exc)


def _shell_safe(value: str) -> str:
    """Single-quote a value for safe embedding in the ``/bin/sh -c`` script."""
    return "'" + value.replace("'", "'\\''") + "'"
