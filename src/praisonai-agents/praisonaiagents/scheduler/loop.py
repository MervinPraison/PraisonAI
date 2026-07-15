"""
Schedule Loop for PraisonAI Agents.

Polls ScheduleRunner for due jobs and fires a callback.
"""

import logging
import os
import socket
import uuid
from praisonaiagents._logging import get_logger
import threading
import time
from typing import Callable, Optional

from .runner import ScheduleRunner
from .protocols import ScheduleStoreProtocol

logger = get_logger(__name__)

class ScheduleLoop:
    """Tick loop that polls a ScheduleRunner and fires due jobs.

    Runs on a **daemon thread** so it never blocks the caller and
    is automatically cleaned up on process exit.

    Example::

        from praisonaiagents.scheduler import ScheduleLoop

        def handle(job):
            print(f"Firing: {job.name} — {job.message}")

        loop = ScheduleLoop(on_trigger=handle, tick_seconds=30)
        loop.start()
        # … later …
        loop.stop()
    """

    def __init__(
        self,
        on_trigger: Callable,
        store: Optional[ScheduleStoreProtocol] = None,
        tick_seconds: float = 30.0,
    ):
        """
        Args:
            on_trigger: Called with each due ``ScheduleJob``.
            store: Schedule store to poll.  Defaults to the global
                   ``FileScheduleStore()``.
            tick_seconds: Seconds between polls (default 30).
        """
        if store is None:
            from .config_store import ConfigYamlScheduleStore
            store = ConfigYamlScheduleStore()
        self._on_trigger = on_trigger
        self._store = store
        self._runner = ScheduleRunner(self._store)
        self._tick = tick_seconds
        self._on_due: Optional[Callable[[], None]] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # Stable per-process identity for atomic job claims (host:pid:uuid) so a
        # due job fires at most once across tickers/processes/hosts when the
        # backing store supports ``claim_due``.
        self._owner_id = (
            f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        )
        self._atomic_claim = self._runner.supports_atomic_claim()

    # ── Public API ──────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """Whether the loop thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def start(
        self,
        on_due: Optional[Callable[[], None]] = None,
        store: Optional[ScheduleStoreProtocol] = None,
    ) -> None:
        """Start the tick loop on a daemon thread.

        Calling ``start()`` when already running is a no-op.

        Satisfies :class:`SchedulerProviderProtocol`. The optional ``on_due``
        and ``store`` arguments let this be driven uniformly with external
        providers; when omitted the loop uses its configured ``on_trigger``
        and store (backward-compatible zero-arg default).

        Args:
            on_due: Optional callback invoked each tick instead of the internal
                claim+fire path — lets an external caller drive *when* firing
                happens while the runner/store still decide *what* fires.
            store: Optional store override applied before starting.
        """
        if store is not None:
            self._store = store
            self._runner = ScheduleRunner(self._store)
            self._atomic_claim = self._runner.supports_atomic_claim()
        self._on_due = on_due

        if self.is_running:
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="schedule-loop", daemon=True
        )
        self._thread.start()
        logger.info("ScheduleLoop started (tick=%ss)", self._tick)

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the loop to stop and wait for the thread to exit.

        Args:
            timeout: Max seconds to wait for the thread to join.
        """
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        logger.info("ScheduleLoop stopped")

    # ── Internal ────────────────────────────────────────────────────────

    def fire_due(self) -> None:
        """Claim and fire all currently-due jobs — one tick's worth of work.

        This is the *what fires* half, kept separate from *when* it is called so
        an external :class:`SchedulerProviderProtocol` can drive firing (on a
        timer, webhook, or cron trigger) without an always-on poll thread. The
        built-in loop simply calls this once per ``tick_seconds``.
        """
        # Reserve due jobs atomically when the store supports it, so a
        # due job fires at most once across processes/hosts; only jobs
        # this ticker won are returned. Falls back to the non-atomic
        # get_due_jobs path when unsupported.
        due = self._runner.claim_due_jobs(self._owner_id, lease_seconds=300)
        for job in due:
            try:
                self._on_trigger(job)
                # Update last_run_at so the job won't re-fire
                # until the next interval elapses.
                job.last_run_at = time.time()
                self._store.update(job)
                self._emit_hook(job)
            except Exception:
                logger.exception(
                    "Error triggering schedule job %s (%s)",
                    job.name, job.id,
                )
            finally:
                # Release the lease so it does not linger until expiry.
                if self._atomic_claim:
                    try:
                        self._runner.complete_run(job.id, self._owner_id)
                    except Exception:
                        logger.exception(
                            "Error releasing lease for schedule job "
                            "%s (%s)",
                            job.name, job.id,
                        )

    def _run(self) -> None:
        """Loop body executed on the daemon thread."""
        while not self._stop_event.is_set():
            try:
                # When an external caller supplied an ``on_due`` callback it
                # decides how a tick is handled; otherwise fire due jobs here.
                if self._on_due is not None:
                    self._on_due()
                else:
                    self.fire_due()
            except Exception:
                logger.exception("ScheduleLoop tick error")

            # Sleep in small increments so stop() is responsive.
            self._stop_event.wait(timeout=self._tick)

    def _emit_hook(self, job) -> None:
        """Best-effort emit of SCHEDULE_TRIGGER notification.

        Logs the trigger event.  Hook-aware callers (e.g. bots) can
        wire a proper ``HookRunner`` externally via the ``on_trigger``
        callback.
        """
        logger.debug(
            "SCHEDULE_TRIGGER: job=%s id=%s", job.name, job.id
        )


# The built-in ``ScheduleLoop`` is the default ``SchedulerProviderProtocol``
# implementation: an always-on daemon thread that polls every ``tick_seconds``.
# Exposed under a provider-oriented name so operators can select firing
# backends uniformly (``in_process`` [default] | external providers in the
# wrapper). This is an alias, not a subclass — zero behaviour change.
InProcessScheduleProvider = ScheduleLoop
