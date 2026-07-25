"""Event-loop liveness watchdog for long-lived gateway loops (Issue #3385).

A gateway process can stay *alive* while its asyncio event loop is **wedged** —
deadlocked, blocked on a synchronous call inside async context, or stuck on an
``await`` that never returns. When that happens every asyncio-based recovery
path (drain, scale-to-zero, reconnect supervision, the ``/live`` HTTP probe)
is structurally unable to fire, because they all run *on* the frozen loop.
Ordinary process supervisors only restart a process that has **exited**, so a
wedged gateway becomes a silent zombie that holds its sockets and answers no
messages until a human kills it.

This module provides a small, dependency-free (pure stdlib) primitive that runs
on a dedicated OS thread — so it keeps working precisely when the loop does
not. It periodically probes the loop via ``loop.call_soon_threadsafe`` and
measures scheduling lag; after *N* consecutive missed probes it declares the
loop wedged, optionally dumps all-thread stacks via :mod:`faulthandler`, and
forces a clean hand-back to the supervisor via ``os._exit`` (bypassing
``Py_FinalizeEx``, which would itself hang joining the stuck threads).

Design principles:

* **Opt-in.** Nothing arms the watchdog unless an embedder calls :meth:`arm`.
* **Fail-open.** Any error inside the watchdog must never wedge or kill a
  healthy gateway. Once armed, it only ever *reacts* to a confirmed stall.
* **No heavy deps.** Only :mod:`threading`, :mod:`faulthandler`, :mod:`os`,
  :mod:`sys`, and :mod:`time` from the stdlib.

The primitive lives in core so every embedder — not just the CLI gateway — can
opt into the same liveness/self-recovery contract around any long-lived loop.
Deployment wiring (systemd ``Type=notify`` / ``WatchdogSec``, CLI flags) is a
wrapper concern and intentionally not part of this module.
"""

from __future__ import annotations

import faulthandler
import math
import os
import sys
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Optional

if TYPE_CHECKING:  # pragma: no cover - typing only
    import asyncio

# Reuse the restart-intent exit-code protocol (Issue #2437): EX_TEMPFAIL (75)
# tells the supervisor "transient failure — please restart".
from .protocols import GATEWAY_RESTART_EXIT_CODE

__all__ = [
    "LoopWatchdogPolicy",
    "LoopWatchdog",
]


@dataclass
class LoopWatchdogPolicy:
    """Configuration for :class:`LoopWatchdog`.

    Attributes:
        probe_interval_s: Seconds between liveness probes scheduled onto the
            loop. Also the cadence at which the watchdog thread wakes.
        missed_probes_before_wedged: Number of *consecutive* probes that must
            fail to round-trip within their budget before the loop is declared
            wedged. With the defaults (5s x 3) a stall of ~15s trips recovery.
        on_wedge: What to do once a wedge is confirmed. ``"dump_and_exit"``
            dumps all-thread stacks then calls ``os._exit(exit_code)``;
            ``"dump_only"`` dumps stacks but leaves the process running (useful
            for observation/testing).
        exit_code: Process exit code used when ``on_wedge == "dump_and_exit"``.
            Defaults to EX_TEMPFAIL (75) so a supervisor restarts the process.
        dump_file: Optional path to also write the stack dump to (in addition
            to stderr). ``None`` writes to stderr only.
    """

    probe_interval_s: float = 5.0
    missed_probes_before_wedged: int = 3
    on_wedge: Literal["dump_and_exit", "dump_only"] = "dump_and_exit"
    exit_code: int = GATEWAY_RESTART_EXIT_CODE
    dump_file: Optional[str] = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.probe_interval_s) or self.probe_interval_s <= 0:
            raise ValueError("probe_interval_s must be a finite value > 0")
        if self.missed_probes_before_wedged < 1:
            raise ValueError("missed_probes_before_wedged must be >= 1")
        if self.on_wedge not in ("dump_and_exit", "dump_only"):
            raise ValueError(
                "on_wedge must be 'dump_and_exit' or 'dump_only'"
            )

    @property
    def wedge_after_s(self) -> float:
        """Approximate stall duration (seconds) before a wedge is declared."""
        return self.probe_interval_s * self.missed_probes_before_wedged


class LoopWatchdog:
    """OS-thread liveness probe for an asyncio loop. Fail-open by design.

    Typical use, wrapping any long-lived loop::

        watchdog = LoopWatchdog()
        watchdog.arm(loop)
        try:
            loop.run_forever()
        finally:
            watchdog.disarm()

    The watchdog thread schedules a no-op callback onto ``loop`` every
    ``probe_interval_s`` seconds via ``loop.call_soon_threadsafe``. A live loop
    runs the callback promptly, resetting the missed-probe counter. A wedged
    loop never runs it; after ``missed_probes_before_wedged`` consecutive
    misses the watchdog reacts per :attr:`LoopWatchdogPolicy.on_wedge`.
    """

    def __init__(self, policy: Optional[LoopWatchdogPolicy] = None) -> None:
        self.policy = policy or LoopWatchdogPolicy()
        self._loop: "Optional[asyncio.AbstractEventLoop]" = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        # Set by the loop each time a probe runs; compared by the watchdog
        # thread to detect misses. Guarded by the GIL for these simple stores.
        self._last_ack = 0.0
        self._last_probe = 0.0
        self._wedged = False

    @property
    def armed(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def wedged(self) -> bool:
        """True once a wedge has been confirmed (mainly for ``dump_only``)."""
        return self._wedged

    def arm(self, loop: "asyncio.AbstractEventLoop") -> None:
        """Start watching ``loop`` from a dedicated daemon OS thread.

        Idempotent: calling :meth:`arm` while already armed is a no-op. Any
        failure to start the thread is swallowed (fail-open) — a watchdog that
        cannot start must never prevent a healthy gateway from running.
        """
        if self.armed:
            return
        try:
            self._loop = loop
            self._stop.clear()
            self._wedged = False
            now = time.monotonic()
            self._last_ack = now
            self._last_probe = now
            self._thread = threading.Thread(
                target=self._run,
                name="praisonai-loop-watchdog",
                daemon=True,
            )
            self._thread.start()
        except Exception:  # pragma: no cover - fail open
            self._thread = None
            self._loop = None

    def disarm(self) -> None:
        """Stop watching. Safe to call multiple times / when not armed."""
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            try:
                thread.join(timeout=self.policy.probe_interval_s + 1.0)
            except Exception:  # pragma: no cover - fail open
                pass
        self._thread = None
        self._loop = None

    def _ack(self) -> None:
        """Callback run *on the loop*; records that the loop is alive."""
        self._last_ack = time.monotonic()

    def _schedule_probe(self) -> bool:
        """Schedule an ack onto the loop. Returns False if scheduling fails."""
        loop = self._loop
        if loop is None:
            return False
        try:
            loop.call_soon_threadsafe(self._ack)
            self._last_probe = time.monotonic()
            return True
        except RuntimeError:
            # Loop is closed / not running — treat as not-scheduled but do not
            # declare a wedge; a closed loop is a normal shutdown, not a hang.
            return False
        except Exception:  # pragma: no cover - fail open
            return False

    def _run(self) -> None:
        interval = self.policy.probe_interval_s
        threshold = self.policy.missed_probes_before_wedged
        missed = 0
        while not self._stop.is_set():
            scheduled = self._schedule_probe()
            # Wait one interval for the loop to run our ack.
            if self._stop.wait(interval):
                break
            if not scheduled:
                # Could not schedule (loop closed / gone). Reset and keep
                # failing open rather than tripping on a normal shutdown.
                missed = 0
                continue
            if self._last_ack >= self._last_probe:
                # Loop ran the ack within the budget: healthy.
                missed = 0
                continue
            # The loop did not run the ack within this interval.
            missed += 1
            if missed >= threshold and not self._wedged:
                self._on_wedge()
                if self.policy.on_wedge == "dump_only":
                    # Keep observing but do not re-fire repeatedly.
                    missed = 0

    def _on_wedge(self) -> None:
        self._wedged = True
        try:
            self._dump_stacks()
        except Exception:  # pragma: no cover - fail open
            pass
        if self.policy.on_wedge == "dump_and_exit":
            # If disarm() raced in while we were dumping stacks, honour the
            # intentional shutdown and do not terminate the process — a
            # deliberate disarm must never trigger a supervisor restart.
            if self._stop.is_set():
                return
            # Bypass Py_FinalizeEx: normal interpreter shutdown would try to
            # join the stuck loop thread and hang. os._exit hands the process
            # straight back to the supervisor.
            try:
                sys.stderr.flush()
            except Exception:  # pragma: no cover - fail open
                pass
            os._exit(self.policy.exit_code)

    def _dump_stacks(self) -> None:
        """Dump all-thread stacks to stderr and, if configured, a file."""
        stall = self.policy.wedge_after_s
        header = (
            f"praisonai-loop-watchdog: event loop wedged "
            f"(no progress for ~{stall:.0f}s); dumping all-thread stacks\n"
        )
        try:
            sys.stderr.write(header)
        except Exception:  # pragma: no cover - fail open
            pass
        try:
            faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
        except Exception:  # pragma: no cover - fail open
            pass
        dump_file = self.policy.dump_file
        if dump_file:
            try:
                # Line-buffered append; keep the fd open across the dump.
                with open(dump_file, "a", encoding="utf-8") as fh:
                    fh.write(header)
                    fh.flush()
                    faulthandler.dump_traceback(file=fh, all_threads=True)
            except Exception:  # pragma: no cover - fail open
                pass
