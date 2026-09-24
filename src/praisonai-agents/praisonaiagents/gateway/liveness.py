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
    "StartupWatchdog",
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
        shutdown_grace_s: Extra budget (seconds) added beyond a caller's
            ``drain_timeout`` when arming the shutdown-phase *deadline* mode
            (:meth:`LoopWatchdog.arm_deadline`). The deadline fires independent
            of loop responsiveness, so a wedged *teardown* on a still-alive loop
            still gets an all-thread stack dump + bounded self-exit rather than
            an external ``SIGKILL`` (Issue #5079).
    """

    probe_interval_s: float = 5.0
    missed_probes_before_wedged: int = 3
    on_wedge: Literal["dump_and_exit", "dump_only"] = "dump_and_exit"
    exit_code: int = GATEWAY_RESTART_EXIT_CODE
    dump_file: Optional[str] = None
    shutdown_grace_s: float = 5.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.probe_interval_s) or self.probe_interval_s <= 0:
            raise ValueError("probe_interval_s must be a finite value > 0")
        if self.missed_probes_before_wedged < 1:
            raise ValueError("missed_probes_before_wedged must be >= 1")
        if self.on_wedge not in ("dump_and_exit", "dump_only"):
            raise ValueError(
                "on_wedge must be 'dump_and_exit' or 'dump_only'"
            )
        if not math.isfinite(self.shutdown_grace_s) or self.shutdown_grace_s < 0:
            raise ValueError("shutdown_grace_s must be a finite value >= 0")

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
        # Continuously-measured scheduling lag (ms) of the most recently
        # acked probe. Read back by the health surface as a saturation signal
        # (Issue #4265) — the same measurement the wedge check already relies
        # on, exposed rather than only compared against the wedge threshold.
        self._probe_sent_at = 0.0
        self._last_lag_ms = 0.0
        # Shutdown-phase deadline mode (Issue #5079). A separate daemon thread
        # + stop event so it is fully independent of the liveness probe loop:
        # the deadline fires on a wall-clock overrun regardless of whether the
        # event loop is still responsive (a wedged *teardown*, not a wedged
        # *loop*), reusing the same stack-dump + os._exit primitive.
        self._deadline_thread: Optional[threading.Thread] = None
        self._deadline_stop = threading.Event()
        self._deadline_expired = False
        # Guards the deadline generation swap (thread + its stop event) so an
        # arm racing a cancel can never mix one generation's thread with
        # another's stop event (Issue #5079 review).
        self._deadline_lock = threading.Lock()

    @property
    def armed(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def deadline_armed(self) -> bool:
        """True while a shutdown-phase deadline is armed (Issue #5079)."""
        return (
            self._deadline_thread is not None
            and self._deadline_thread.is_alive()
        )

    @property
    def deadline_expired(self) -> bool:
        """True once a shutdown deadline expired (mainly for ``dump_only``)."""
        return self._deadline_expired

    @property
    def last_lag_ms(self) -> float:
        """Most recent event-loop scheduling lag in milliseconds.

        The delay between scheduling a probe and the loop running its ack.
        ``0.0`` until the first probe round-trips. Read by the gateway health
        surface as a forward saturation signal (Issue #4265).
        """
        return self._last_lag_ms

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

    # ── Shutdown-phase deadline mode (Issue #5079) ──────────────────────────

    def arm_deadline(self, deadline_s: float) -> None:
        """Arm a wall-clock shutdown deadline on a dedicated daemon thread.

        Unlike the liveness probe (which only reacts to a *wedged loop*), this
        fires after ``deadline_s`` seconds regardless of loop responsiveness —
        so a teardown coroutine that blocks while the loop is still alive still
        gets an all-thread stack dump + bounded ``os._exit`` instead of being
        left to an external ``SIGKILL``. Callers arm this at the *start* of the
        stop path and :meth:`cancel` it the instant a clean stop completes, so a
        healthy shutdown never self-exits.

        Idempotent and fail-open: a re-arm while already armed is a no-op, and
        any failure to start the thread is swallowed.
        """
        if not math.isfinite(deadline_s) or deadline_s <= 0:
            return
        with self._deadline_lock:
            if self.deadline_armed:
                return
            # Each armed generation gets its *own* stop event, handed directly
            # to the thread. Cancellation state is therefore per-generation: a
            # later arm never clears an older thread's event, so a slow old
            # generation (e.g. still flushing a stack dump) can never observe a
            # fresh generation's cleared flag and self-exit during a healthy run
            # (Issue #5079 review).
            stop = threading.Event()
            self._deadline_expired = False
            try:
                thread = threading.Thread(
                    target=self._run_deadline,
                    args=(deadline_s, stop),
                    name="praisonai-shutdown-watchdog",
                    daemon=True,
                )
                thread.start()
            except Exception:  # pragma: no cover - fail open
                self._deadline_thread = None
                self._deadline_stop = stop
                return
            self._deadline_thread = thread
            self._deadline_stop = stop

    def cancel(self) -> None:
        """Cancel an armed shutdown deadline. Safe when not armed.

        A clean stop() calls this so the bounded self-exit never fires on a
        healthy shutdown. Sets the *current* generation's stop event (so that
        exact thread suppresses its self-exit even if it is mid-dump) and drops
        the reference; a later arm starts a fresh generation with its own event.
        """
        with self._deadline_lock:
            self._deadline_stop.set()
            thread = self._deadline_thread
            self._deadline_thread = None
        if thread is not None and thread is not threading.current_thread():
            try:
                thread.join(timeout=1.0)
            except Exception:  # pragma: no cover - fail open
                pass

    def _run_deadline(self, deadline_s: float, stop: "threading.Event") -> None:
        # Wait out the deadline against *this generation's* event; a clean
        # cancel() sets it and returns immediately so a healthy shutdown never
        # trips the self-exit.
        if stop.wait(deadline_s):
            return
        self._on_deadline(deadline_s, stop)

    def _on_deadline(self, deadline_s: float, stop: "threading.Event") -> None:
        # Only the still-active generation records expiry / self-exits: if this
        # thread was cancelled its own ``stop`` is set, so a stale generation
        # that survived a bounded join stays inert.
        if stop.is_set():
            return
        self._deadline_expired = True
        try:
            self._dump_stacks(
                reason=(
                    f"graceful shutdown did not complete within "
                    f"~{deadline_s:.0f}s"
                )
            )
        except Exception:  # pragma: no cover - fail open
            pass
        if self.policy.on_wedge == "dump_and_exit":
            # If cancel() raced in while we were dumping, honour the clean stop.
            if stop.is_set():
                return
            try:
                sys.stderr.flush()
            except Exception:  # pragma: no cover - fail open
                pass
            os._exit(self.policy.exit_code)

    def _ack(self) -> None:
        """Callback run *on the loop*; records that the loop is alive."""
        now = time.monotonic()
        self._last_ack = now
        # Record the scheduling lag: how long the loop took to run this ack
        # after we scheduled it. This is the same signal the wedge check uses,
        # exposed as a gauge for the health surface (Issue #4265).
        #
        # ``_probe_sent_at`` is anchored to the *oldest still-unacked* probe,
        # not the most recent one: when the loop stalls across several probe
        # intervals the watchdog keeps scheduling fresh acks that all queue
        # behind the wedge, and measuring from the newest probe would report a
        # fraction of the true stall. Consuming the anchor here (setting it to
        # 0.0) lets the next scheduled probe re-anchor from a caught-up loop.
        sent = self._probe_sent_at
        if sent:
            self._last_lag_ms = max(0.0, (now - sent) * 1000.0)
            self._probe_sent_at = 0.0

    def _schedule_probe(self) -> bool:
        """Schedule an ack onto the loop. Returns False if scheduling fails."""
        loop = self._loop
        if loop is None:
            return False
        try:
            # Only (re-)anchor the lag clock when the previous probe has been
            # acked (``_ack`` zeroes ``_probe_sent_at``). If the loop is stalled
            # and earlier probes are still queued, keep the anchor pinned to the
            # oldest unacked probe so the reported lag reflects the full stall
            # rather than the gap since the newest probe (Issue #4265).
            now = time.monotonic()
            if not self._probe_sent_at:
                self._probe_sent_at = now
            loop.call_soon_threadsafe(self._ack)
            self._last_probe = now
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

    def _dump_stacks(self, reason: Optional[str] = None) -> None:
        """Dump all-thread stacks to stderr and, if configured, a file."""
        if reason is None:
            stall = self.policy.wedge_after_s
            reason = f"event loop wedged (no progress for ~{stall:.0f}s)"
        header = (
            f"praisonai-loop-watchdog: {reason}; "
            f"dumping all-thread stacks\n"
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


class StartupWatchdog:
    """Front-rung liveness guard for the pre-loop startup window (Issue #5265).

    :class:`LoopWatchdog` only becomes meaningful once the asyncio event loop
    is running — it probes the loop via ``loop.call_soon_threadsafe``, so it can
    do nothing before a loop exists. That leaves the window between process
    entry and "loop is live" (heavy imports, config/secret loading, the initial
    adapter ``connect()``\\ s) uncovered. A wedge there — a hanging SDK import, a
    blocking synchronous DNS/network call while minting credentials, a deadlock
    inside ``connect()`` — leaves the process *alive but making no progress*: it
    holds no serving loop, answers no probes, and never exits, so an external
    supervisor never restarts it. It becomes a silent zombie with no diagnostics.

    This primitive closes that gap. It arms a wall-clock **deadline** on a
    dedicated daemon OS thread *before* the heavy work begins, so it keeps
    working precisely when the main thread is wedged. If the deadline elapses
    without :meth:`confirm_loop_live`, it dumps all-thread stacks via
    :mod:`faulthandler` (so the hang is diagnosable) and hands the process back
    to the supervisor via ``os._exit`` with a restart-intent code. A legitimately
    slow-but-alive boot extends the deadline via :meth:`report_startup_progress`
    (bounded, so a truly wedged phase still trips). :meth:`confirm_loop_live`
    disarms it the instant the serving loop begins — at which point
    :class:`LoopWatchdog` takes over.

    Design mirrors :class:`LoopWatchdog`: **opt-in** (nothing arms it unless the
    embedder calls :meth:`arm`), **fail-open** (any error inside the watchdog
    must never kill a healthy startup), and **stdlib-only** (it must run when the
    rest of the process cannot, so its correctness cannot depend on the code it
    guards). Typical use at the gateway entry point::

        sw = StartupWatchdog()
        sw.arm(deadline_s=config.startup_watchdog_timeout)
        load_config(config);   sw.report_startup_progress("config loaded")
        connect_adapters();    sw.report_startup_progress("adapters connected")
        loop = asyncio.new_event_loop()
        LoopWatchdog().arm(loop)
        sw.confirm_loop_live()  # disarm; loop watchdog now owns liveness
        loop.run_forever()
    """

    def __init__(
        self,
        *,
        on_expire: Literal["dump_and_exit", "dump_only"] = "dump_and_exit",
        exit_code: int = GATEWAY_RESTART_EXIT_CODE,
        dump_file: Optional[str] = None,
        max_extensions: int = 10,
    ) -> None:
        if on_expire not in ("dump_and_exit", "dump_only"):
            raise ValueError(
                "on_expire must be 'dump_and_exit' or 'dump_only'"
            )
        if max_extensions < 0:
            raise ValueError("max_extensions must be >= 0")
        self.on_expire = on_expire
        self.exit_code = exit_code
        self.dump_file = dump_file
        self.max_extensions = max_extensions
        self._thread: Optional[threading.Thread] = None
        # Each armed generation gets its own stop event handed straight to the
        # thread, so a confirm/re-arm race can never let a stale generation
        # observe a fresh generation's cleared flag and self-exit (mirrors the
        # per-generation discipline of LoopWatchdog's deadline mode). The stop
        # event, once set, stays set: a healthy confirm/disarm is monotonic.
        self._stop = threading.Event()
        # A separate wake event carries progress reports: it is briefly set to
        # nudge the waiting thread to re-read the (extended) deadline, then
        # cleared. Keeping it distinct from _stop means a progress nudge can
        # never be mistaken for a disarm (and vice versa).
        self._wake = threading.Event()
        self._deadline_s = 0.0
        self._extensions_used = 0
        self._expired = False
        self._confirmed = False
        self._lock = threading.Lock()

    @property
    def armed(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def expired(self) -> bool:
        """True once the startup deadline expired (mainly for ``dump_only``)."""
        return self._expired

    @property
    def confirmed(self) -> bool:
        """True once :meth:`confirm_loop_live` has disarmed the watchdog."""
        return self._confirmed

    def arm(self, *, deadline_s: float, dump_stacks: bool = True) -> None:
        """Arm a startup deadline on a dedicated daemon thread. Fail-open.

        Idempotent: arming while already armed is a no-op. A non-finite or
        non-positive ``deadline_s`` is ignored (nothing to guard). ``dump_stacks``
        toggles the all-thread stack dump on expiry.
        """
        if not math.isfinite(deadline_s) or deadline_s <= 0:
            return
        with self._lock:
            if self.armed:
                return
            stop = threading.Event()
            wake = threading.Event()
            self._stop = stop
            self._wake = wake
            self._deadline_s = deadline_s
            self._extensions_used = 0
            self._expired = False
            self._confirmed = False
            self._dump_stacks_on_expire = dump_stacks
            try:
                thread = threading.Thread(
                    target=self._run,
                    args=(stop, wake),
                    name="praisonai-startup-watchdog",
                    daemon=True,
                )
                thread.start()
            except Exception:  # pragma: no cover - fail open
                self._thread = None
                return
            self._thread = thread

    def report_startup_progress(self, phase: str) -> None:
        """Signal forward progress, extending the deadline by one interval.

        A legitimately slow boot (e.g. many adapters, cold DNS) calls this at
        each phase so it is not killed. Extensions are bounded by
        ``max_extensions`` so a phase that itself wedges still trips the
        deadline. Fail-open and a no-op when not armed.
        """
        if not self.armed:
            return
        with self._lock:
            if self._extensions_used >= self.max_extensions:
                return
            self._extensions_used += 1
            wake = self._wake
        # Wake the waiting thread so it re-reads the extended deadline. The
        # thread resets its window on any wake, then clears the event and keeps
        # waiting against its own (still-unset) stop event.
        wake.set()

    def confirm_loop_live(self) -> None:
        """Disarm the startup watchdog; the event loop is now live.

        Called immediately before :class:`LoopWatchdog` is armed. Safe to call
        multiple times / when not armed. Sets the *current* generation's stop
        event so that exact thread suppresses its self-exit even if it is
        mid-dump, then drops the reference.
        """
        with self._lock:
            self._confirmed = True
            self._stop.set()
            # Nudge the thread out of its wait immediately so the join is prompt.
            self._wake.set()
            thread = self._thread
            self._thread = None
        if thread is not None and thread is not threading.current_thread():
            try:
                thread.join(timeout=1.0)
            except Exception:  # pragma: no cover - fail open
                pass

    def _run(self, stop: "threading.Event", wake: "threading.Event") -> None:
        # Wait out the deadline against *this generation's* events. ``stop`` is
        # set (and stays set) by a confirm/disarm — that must break us out and
        # suppress the self-exit. ``wake`` is a transient progress nudge — on
        # each wake we reset the window and keep waiting. A plain timeout with
        # neither event set means the startup genuinely wedged.
        start = time.monotonic()
        while not stop.is_set():
            remaining = (start + self._deadline_s) - time.monotonic()
            if remaining <= 0:
                break
            if wake.wait(remaining):
                wake.clear()
                if stop.is_set():
                    return
                # A progress report: extend the window and keep waiting.
                start = time.monotonic()
                continue
        self._on_expire(stop)

    def _on_expire(self, stop: "threading.Event") -> None:
        # Only fire if this generation was not disarmed. A confirm_loop_live()
        # that raced in has set this exact event, so a stale generation stays
        # inert and never self-exits a healthy startup.
        if stop.is_set():
            return
        self._expired = True
        if getattr(self, "_dump_stacks_on_expire", True):
            try:
                self._dump_stacks()
            except Exception:  # pragma: no cover - fail open
                pass
        if self.on_expire == "dump_and_exit":
            # If confirm_loop_live() raced in while we were dumping, honour it.
            if stop.is_set():
                return
            try:
                sys.stderr.flush()
            except Exception:  # pragma: no cover - fail open
                pass
            os._exit(self.exit_code)

    def _dump_stacks(self) -> None:
        reason = (
            f"gateway startup did not confirm a live event loop within "
            f"~{self._deadline_s:.0f}s"
        )
        header = (
            f"praisonai-startup-watchdog: {reason}; "
            f"dumping all-thread stacks\n"
        )
        try:
            sys.stderr.write(header)
        except Exception:  # pragma: no cover - fail open
            pass
        try:
            faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
        except Exception:  # pragma: no cover - fail open
            pass
        dump_file = self.dump_file
        if dump_file:
            try:
                with open(dump_file, "a", encoding="utf-8") as fh:
                    fh.write(header)
                    fh.flush()
                    faulthandler.dump_traceback(file=fh, all_threads=True)
            except Exception:  # pragma: no cover - fail open
                pass
